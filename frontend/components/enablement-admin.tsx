"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { adminApiFetch as apiFetch } from "./auth-provider";
import styles from "./enablement-admin.module.css";
type Metadata = {
    title: string;
    summary: string;
    source_url: string;
    [key: string]: string | string[] | number | null;
};
type Row = {
    source_id: string;
    metadata: Metadata;
    revision: number;
    status: string;
    published_version: number | null;
    system_visible: boolean;
    model_allowed: boolean;
    partner_allowed: boolean;
    published_metadata?: Metadata;
    versions: {
        version: number;
        published_at: string;
    }[];
};
type Category = {
    id: string;
    kind: "role" | "zone";
    name: string;
    sort_order: number;
};
const statusText: Record<string, string> = { draft: "草稿", published: "已发布", unpublished: "已下架", revoked: "已撤销授权" };
const resourceDefaults: Metadata = { title: "", summary: "", source_url: "", resource_type: "course", role_ids: [], zone_ids: [], level: "basic", duration_minutes: null, course_goals: "", audience: "", outline: "", cover_url: "", lab_goals: "", lab_requirements: "" };
async function call(path: string, method = "GET", body?: unknown, timeoutMs?: number) {
    const response = await apiFetch(path, { method, timeoutMs, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(typeof data?.detail === "string" ? data.detail : response.status === 422 ? "请检查必填字段、分类和来源链接。" : "操作失败，请稍后重试。");
    }
    return response.json();
}
export function ResourceManager() {
    const [rows, setRows] = useState<Row[]>([]);
    const [selected, setSelected] = useState<string | null>(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [notice, setNotice] = useState("");
    const [checked, setChecked] = useState<string[]>([]);
    const [typeFilter, setTypeFilter] = useState("");
    const [statusFilter, setStatusFilter] = useState("");
    const [categoryRefresh, setCategoryRefresh] = useState(0);
    const fileInput = useRef<HTMLInputElement>(null);
    const load = useCallback(async () => { setLoading(true); try {
        setRows(await call('/admin/enablement/resources'));
        setChecked([]);
        setError("");
    }
    catch (e) {
        setError((e as Error).message);
    }
    finally {
        setLoading(false);
    } }, []);
    useEffect(() => { void load(); }, [load]);
    const visibleRows = rows.filter(row => (!typeFilter || row.metadata.resource_type === typeFilter) && (!statusFilter || row.status === statusFilter));
    async function download(template = false) {
        setBusy(true); setError(""); setNotice("");
        try {
            const response = await apiFetch(`/admin/enablement/resources/${template ? 'template' : 'export'}`);
            if (!response.ok) {
                const data = await response.json().catch(() => null);
                throw new Error(typeof data?.detail === 'string' ? data.detail : '导出失败，请稍后重试。');
            }
            const url = URL.createObjectURL(await response.blob());
            const link = document.createElement('a');
            link.href = url; link.download = template ? '伴飞课程与实验导入模板.xlsx' : '伴飞课程与实验.xlsx';
            document.body.appendChild(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            setNotice(template ? '模板已下载，按表头和使用说明填写后导入。' : '已导出全部课程与实验，可直接修改表格后导入。');
        } catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
    }
    async function upload(file: File) {
        setError(""); setNotice("");
        if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 10 * 1024 * 1024) {
            setError('请选择不超过10MB的.xlsx文件。'); return;
        }
        if (!window.confirm('导入将按表格更新资源草稿和三项用途授权，同ID资源会更新。减少授权会立即限制旧版本使用。内容需另行上架，是否继续？')) return;
        setBusy(true);
        try {
            const body = new FormData(); body.append('file', file);
            const response = await apiFetch('/admin/enablement/resources/import', {method: 'POST', body, timeoutMs: 120_000});
            const data = await response.json();
            if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : '导入失败，请检查表格内容。');
            await load(); setCategoryRefresh(value => value + 1);
            setNotice(`导入完成：新增 ${data.created} 条，更新 ${data.updated} 条，未变化 ${data.unchanged} 条。内容已保存，需发布时请勾选后批量上架。`);
        } catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
    }
    async function batch(action: 'publish' | 'unpublish') {
        const label = action === 'publish' ? '上架' : '下架';
        const explanation = action === 'publish' ? '将发布选中资源当前已保存的草稿，沿用各自用途授权。' : '将下架选中资源中的已发布资源，保留历史版本。';
        if (!window.confirm(`${explanation}\n确认批量${label} ${checked.length} 条资源？`)) return;
        setBusy(true); setError(""); setNotice("");
        try {
            const result = await call('/admin/enablement/resources/batch', 'POST', {action, items: rows.filter(row => checked.includes(row.source_id)).map(row => ({source_id: row.source_id, base_revision: row.revision}))}, 120_000);
            await load();
            setNotice(`已${label} ${result.changed} 条${result.skipped ? `，跳过 ${result.skipped} 条未上架资源` : ''}。`);
        } catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
    }
    return <main className="page"><p className="eyebrow">Partner Enablement</p><div className="section-heading-row"><div><h1>课程与实验资源</h1><p className="lead">按岗位和专区维护课程、实验，学习和实践在来源平台完成。</p></div>{selected === null && <div className={styles.actions}>
        <button className="secondary-btn" disabled={busy || loading} onClick={() => void download()}>导出全部 Excel</button>
        <button className="secondary-btn" disabled={busy || loading} onClick={() => void download(true)}>下载导入模板</button>
        <button className="secondary-btn" disabled={busy || loading} onClick={() => fileInput.current?.click()}>导入 Excel</button>
        <input ref={fileInput} type="file" accept=".xlsx" aria-label="导入课程与实验文件" hidden onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void upload(file); }}/>
        <button disabled={busy} onClick={() => { setNotice(''); setSelected("new"); }}>新增资源</button>
    </div>}</div>
    {error && <p role="alert">{error} <button disabled={busy} onClick={() => void load()}>重新加载</button></p>}
    {notice && selected === null && <p role="status" className={styles.notice}>{notice}</p>}
    {selected !== null ? <EnablementEditor key={selected} sourceId={selected === "new" ? undefined : selected} onSaved={row => { if (selected === "new")
            setSelected(row.source_id); void load(); }} onClose={() => setSelected(null)}/> :
            <section className="card">
                <div className={styles.listControls}>
                    <fieldset disabled={busy || loading} className={styles.toolbar}>
                        <div className={styles.filters}>
                            <label>类型<select aria-label="筛选资源类型" value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setChecked([]); }}><option value="">全部类型</option><option value="course">课程</option><option value="lab">实验</option></select></label>
                            <label>状态<select aria-label="筛选发布状态" value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setChecked([]); }}><option value="">全部状态</option>{Object.entries(statusText).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                        </div>
                        <div className={styles.batchActions}>
                            <span className={styles.selectionCount}>已选 {checked.length} 条</span>
                            <button disabled={!checked.length} onClick={() => void batch('publish')}>批量上架</button>
                            <button className="secondary-btn" disabled={!checked.length} onClick={() => void batch('unpublish')}>批量下架</button>
                        </div>
                    </fieldset>
                    <p className={styles.transferHint}><span>新增可下载空白模板，批量修改可先导出。</span><span>导入保存草稿，上架发布已保存内容并沿用用途授权。</span></p>
                </div>
                {busy && <p aria-live="polite">处理中，请稍候…</p>}
                {loading ? <p>加载中…</p> : visibleRows.length === 0 ? <p>暂无符合条件的课程或实验资源。</p> : <div className={styles.tableWrap}><table className={`data-table ${styles.table}`}><thead><tr><th><input type="checkbox" aria-label="选择当前筛选的全部资源" disabled={busy} checked={visibleRows.length > 0 && visibleRows.every(row => checked.includes(row.source_id))} onChange={e => setChecked(e.target.checked ? visibleRows.map(row => row.source_id) : [])}/></th><th>资源名称</th><th>类型</th><th>发布状态</th><th>当前发布版本</th><th>操作</th></tr></thead><tbody>{visibleRows.map(row => <tr key={row.source_id}><td><input type="checkbox" aria-label={`选择资源 ${row.metadata.title}`} disabled={busy} checked={checked.includes(row.source_id)} onChange={e => setChecked(ids => e.target.checked ? [...ids, row.source_id] : ids.filter(id => id !== row.source_id))}/></td><td><strong>{row.metadata.title}</strong></td><td>{row.metadata.resource_type === "course" ? "课程" : "实验"}</td><td>{statusText[row.status]}</td><td>{row.published_version ? `V${row.published_version}` : "尚未发布"}</td><td><button className="secondary-btn" disabled={busy} onClick={() => setSelected(row.source_id)}>管理资源</button></td></tr>)}</tbody></table></div>}
            </section>}
    {selected === null && <CategoryManager key={categoryRefresh} />}
  </main>;
}
function EnablementEditor({ sourceId, onSaved, onClose }: {
    sourceId?: string;
    onSaved?: (row: Row) => void;
    onClose?: () => void;
}) {
    const [row, setRow] = useState<Row | null>(null);
    const [metadata, setMetadata] = useState<Metadata>(resourceDefaults);
    const [categories, setCategories] = useState<Category[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [permissions, setPermissions] = useState({ system_visible: false, model_allowed: false, partner_allowed: false });
    const [reason, setReason] = useState("");
    const endpoint = `/admin/enablement/resources${sourceId ? `/${sourceId}` : ""}`;
    const accept = useCallback((next: Row) => { setRow(next); setMetadata(next.metadata); setPermissions({ system_visible: !!next.system_visible, model_allowed: !!next.model_allowed, partner_allowed: !!next.partner_allowed }); }, []);
    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            setCategories(await call('/admin/enablement/resource-categories'));
            if (sourceId) {
                const response = await apiFetch(endpoint);
                if (!response.ok) {
                    throw new Error("配置加载失败，请重试。");
                }
                else
                    accept(await response.json());
            }
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setLoading(false);
        }
    }, [sourceId, endpoint, accept]);
    useEffect(() => { void load(); }, [load]);
    const dirty = row !== null && JSON.stringify(metadata) !== JSON.stringify(row.metadata);
    function field(key: string, value: string | number | null | string[]) { setMetadata(m => ({ ...m, [key]: value })); }
    async function action(suffix: string, body: object, method = "POST", success = "操作已保存") {
        setBusy(true);
        setError("");
        setNotice("");
        try {
            const next = await call(endpoint + suffix, method, body);
            accept(next);
            setNotice(success);
            onSaved?.(next);
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setBusy(false);
        }
    }
    function save(e: FormEvent) { e.preventDefault(); void action("", { base_revision: row?.revision || 0, metadata }, sourceId ? "PUT" : "POST", "草稿已保存，可发布新版本。"); }
    const textInput = (key: string, label: string, required = false, multiline = false) => <label key={key} className={multiline ? styles.wide : ""}>{label}{multiline ? <textarea aria-label={label} rows={3} maxLength={key === "outline" ? 12000 : 4000} required={required} value={String(metadata[key] ?? "")} onChange={e => field(key, e.target.value)}/> : <input aria-label={label} maxLength={2000} required={required} value={String(metadata[key] ?? "")} onChange={e => field(key, e.target.value)}/>}</label>;
    const canPublish = !!metadata.level;
    if (loading)
        return <section className="card">加载配置中…</section>;
    return <div className={styles.stack}>
    {error && <div role="alert" className={styles.error}>{error} <button className="secondary-btn" onClick={() => void load()}>重新加载</button></div>}
    {notice && <p role="status" className={styles.notice}>{notice}</p>}
    <section className="card"><div className="section-heading-row"><h2>{row ? "资源草稿" : "新增资源"}</h2><span>{row ? `${statusText[row.status]} · 编辑修订 ${row.revision}` : "尚未保存"}</span></div>
      <form onSubmit={save}><fieldset disabled={busy} className={styles.form}>
        {<label>资源类型<select aria-label="资源类型" value={String(metadata.resource_type)} disabled={!!row} onChange={e => setMetadata(m => ({ ...resourceDefaults, title: m.title, summary: m.summary, source_url: m.source_url, role_ids: m.role_ids, zone_ids: m.zone_ids, level: m.level, duration_minutes: e.target.value === "lab" ? m.duration_minutes : null, resource_type: e.target.value }))}><option value="course">课程</option><option value="lab">实验</option></select></label>}
        {textInput('title', '资源名称', true)}{textInput('summary', '简介', true, true)}
        {<>
          {([['role_ids', '岗位', 'role'], ['zone_ids', '专区', 'zone']] as const).map(([key, label, kind]) => <div key={key} className={styles.wide}><p>{label}（可多选）</p><div className={styles.tags}>{categories.filter(c => c.kind === kind).map(c => <label key={c.id}><input type="checkbox" checked={(metadata[key] as string[]).includes(c.id)} onChange={e => field(key, e.target.checked ? [...(metadata[key] as string[]), c.id] : (metadata[key] as string[]).filter(id => id !== c.id))}/>{c.name}</label>)}</div></div>)}
          <label>层级<select aria-label="层级" required value={String(metadata.level || "")} onChange={e => field('level', e.target.value)}><option value="" disabled>请选择层级</option><option value="basic">基础</option><option value="advanced">进阶</option></select></label>
          {metadata.resource_type === 'lab' && <label>时长（分钟）<input aria-label="时长（分钟）" type="number" min={1} max={100000} value={metadata.duration_minutes === null ? "" : Number(metadata.duration_minutes)} onChange={e => field('duration_minutes', e.target.value === "" ? null : Number(e.target.value))}/></label>}
          {metadata.resource_type === 'course' ? <>{textInput('course_goals', '课程目标', false, true)}{textInput('audience', '目标学员', false, true)}{textInput('outline', '课程大纲', false, true)}{textInput('cover_url', '封面链接（可选）')}</> : <>{textInput('lab_goals', '实验目标', false, true)}{textInput('lab_requirements', '基本要求', false, true)}</>}
        </>}
        {textInput('source_url', '跳转链接', true)}

        <div className={styles.actions}><button type="submit">{busy ? "处理中…" : "保存草稿"}</button>{onClose && <button type="button" className="secondary-btn" onClick={onClose}>返回列表</button>}</div>
      </fieldset></form><p className={styles.hint}>保存草稿不会更新已发布内容。</p>
    </section>
    {row && <>
      {dirty && <p className={styles.notice}>草稿有未保存的修改，请先保存，再进行授权或发布。</p>}
      <section className="card"><h2>用途授权</h2><p>三个用途分别授权，默认关闭。减少授权后，旧版本须重新发布才能使用。</p><fieldset disabled={busy || dirty} className={styles.form}>
        <div className={`${styles.tags} ${styles.wide}`}>{([['system_visible', '系统内可见'], ['model_allowed', '允许发送模型'], ['partner_allowed', '允许对伙伴外发']] as const).map(([key, label]) => <label key={key}><input type="checkbox" checked={permissions[key]} onChange={e => setPermissions(p => ({ ...p, [key]: e.target.checked }))}/>{label}</label>)}</div>
        <label className={styles.wide}>授权或下架原因<input aria-label="授权或下架原因" value={reason} maxLength={500} onChange={e => setReason(e.target.value)}/></label>
        <div className={styles.actions}><button type="button" className="secondary-btn" disabled={!reason.trim()} onClick={() => void action('/permissions', { base_revision: row.revision, ...permissions, reason }, 'PATCH', '用途授权已保存，可发布当前修订。')}>保存用途授权</button></div>
      </fieldset></section>
      <section className="card"><h2>{"发布管理"}</h2><fieldset disabled={busy || dirty} className={styles.form}>

        <div className={styles.actions}><button type="button" disabled={!canPublish} onClick={() => void action('/publish', { base_revision: row.revision }, 'POST', '已发布新的独立版本。')}>发布新版本</button><button type="button" className="secondary-btn" disabled={!reason.trim() || row.status !== 'published'} onClick={() => void action('/unpublish', { base_revision: row.revision, reason, sensitive: false }, 'POST', '已下架，历史版本保留。')}>普通下架</button><button type="button" className="secondary-btn danger-outline" disabled={!reason.trim()} onClick={() => void action('/unpublish', { base_revision: row.revision, reason, sensitive: true }, 'POST', '授权已撤销，受影响内容停止使用。')}>敏感内容撤权</button></div>
      </fieldset>

      </section>
      <section className="card"><h2>发布版本记录</h2>{row.versions.length === 0 ? <p>尚无发布版本。</p> : <><ul>{row.versions.map(v => <li key={v.version}>V{v.version} · {new Date(v.published_at).toLocaleString('zh-CN')}{v.version === row.published_version ? ' · 当前发布指针' : ''}</li>)}</ul><h3>当前发布快照</h3><p>{row.published_metadata?.title}</p><p className={styles.preserve}>{row.published_metadata?.summary}</p><p className={styles.hint}>这是管理员审计内容。实际使用还须检查当前发布状态和用途授权。</p></>}</section>
    </>}
  </div>;
}
function CategoryManager() {
    const [rows, setRows] = useState<Category[]>([]), [kind, setKind] = useState<"role" | "zone">("role");
    const [name, setName] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false);
    useEffect(() => { call('/admin/enablement/resource-categories').then(setRows).catch(e => setError(e.message)); }, []);
    async function save(row?: Category) {
        setBusy(true);
        setError("");
        try {
            await call('/admin/enablement/resource-categories' + (row ? `/${row.id}` : ''), row ? 'PATCH' : 'POST', row ? { name: row.name, sort_order: row.sort_order } : { kind, name, sort_order: Math.max(-1, ...rows.filter(r => r.kind === kind).map(r => r.sort_order)) + 1 });
            setRows(await call('/admin/enablement/resource-categories'));
            if (!row)
                setName("");
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setBusy(false);
        }
    }
    return <details className="card resource-category-admin"><summary>管理岗位 / 专区分类</summary><p className="muted">课程和实验共用分类；排序数值越小越靠前，改名不会改变资源关联。</p>{error && <p role="alert">{error}</p>}
    <form onSubmit={e => { e.preventDefault(); void save(); }} className={`${styles.form} ${styles.categoryForm}`}><label>分类类型<select aria-label="分类类型" value={kind} onChange={e => setKind(e.target.value as "role" | "zone")}><option value="role">岗位</option><option value="zone">专区</option></select></label><label>新分类名称<input required maxLength={80} value={name} onChange={e => setName(e.target.value)}/></label><button disabled={busy || !name.trim()}>新增分类</button></form>
    <div className={styles.tableWrap}><table className="data-table"><thead><tr><th>类型</th><th>分类名称</th><th>排序</th><th>操作</th></tr></thead><tbody>{rows.map((row, i) => <tr key={row.id}><td>{row.kind === 'role' ? '岗位' : '专区'}</td><td><input aria-label={`分类名称 ${row.id}`} value={row.name} maxLength={80} onChange={e => setRows(rs => rs.map((r, j) => j === i ? { ...r, name: e.target.value } : r))}/></td><td><input aria-label={`排序 ${row.id}`} type="number" min={0} max={100000} value={row.sort_order} onChange={e => setRows(rs => rs.map((r, j) => j === i ? { ...r, sort_order: Number(e.target.value) } : r))}/></td><td><button className="secondary-btn" disabled={busy || !row.name.trim()} onClick={() => void save(row)}>保存分类</button></td></tr>)}</tbody></table></div>
  </details>;
}
