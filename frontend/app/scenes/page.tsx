"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ENABLED_SCENES, SCENE_CATEGORIES } from "@/lib/scenes";
import { UiIcon, type IconName } from "@/components/ui-icons";

type CategoryFilter = (typeof SCENE_CATEGORIES)[number];

const STATUS_TEXT = {
  ready: "可使用",
  embedded: "随匹配生成",
  building: "能力建设中",
} as const;

function sceneIcon(category: string): IconName {
  if (category === "智能匹配") return "spark";
  if (category === "伙伴洞察") return "users";
  if (category === "能力发展") return "chart";
  if (category === "项目机会") return "file";
  return "grid";
}

function sceneTone(category: string): string {
  if (category === "智能匹配") return "match";
  if (category === "伙伴洞察") return "partner";
  if (category === "能力发展") return "capability";
  if (category === "项目机会") return "opportunity";
  return "operations";
}

export default function ScenesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedCategory = searchParams.get("category");
  const initialCategory = SCENE_CATEGORIES.includes(requestedCategory as CategoryFilter)
    ? requestedCategory as CategoryFilter
    : "全部";
  const [category, setCategory] = useState<CategoryFilter>(initialCategory);
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(6);

  useEffect(() => {
    setCategory(initialCategory);
  }, [initialCategory]);

  const filteredScenes = useMemo(() => {
    const query = keyword.trim().toLocaleLowerCase("zh-CN");
    return ENABLED_SCENES.filter((scene) => {
      const categoryMatched = category === "全部" || scene.category === category;
      const searchable = [scene.name, scene.description, ...scene.tags, ...scene.exampleQueries].join(" ").toLocaleLowerCase("zh-CN");
      return categoryMatched && (!query || searchable.includes(query));
    });
  }, [category, keyword]);
  const totalPages = Math.max(1, Math.ceil(filteredScenes.length / pageSize));
  const visibleScenes = filteredScenes.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => { setPage(1); }, [category, keyword, pageSize]);

  function selectCategory(nextCategory: CategoryFilter) {
    setCategory(nextCategory);
    const params = new URLSearchParams(searchParams.toString());
    if (nextCategory === "全部") params.delete("category");
    else params.set("category", nextCategory);
    const query = params.toString();
    router.replace(query ? `/scenes?${query}` : "/scenes", { scroll: false });
  }

  return (
    <main className="page scenes-page">
      <section className="scenes-hero">
        <h1>场景广场</h1>
      </section>

      <section className="scene-toolbar" aria-label="场景筛选">
        <div className="scene-category-tabs" role="tablist" aria-label="场景分类">
          {SCENE_CATEGORIES.map((item) => (
            <button key={item} type="button" role="tab" aria-selected={category === item} className={category === item ? "active" : ""} onClick={() => selectCategory(item)}>{item}</button>
          ))}
        </div>
        <div className="scene-search">
          <UiIcon name="search" size={18} />
          <label htmlFor="scene-search" className="sr-only">搜索场景</label>
          <input id="scene-search" type="search" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索场景名称、描述或标签" />
          {keyword && <button type="button" onClick={() => setKeyword("")} aria-label="清空搜索">×</button>}
        </div>
      </section>

      <div className="scene-result-summary">
        <span>{category === "全部" ? "全部场景" : category}</span>
        <small>找到 {filteredScenes.length} 个场景</small>
      </div>

      {filteredScenes.length > 0 ? (
        <>
          <section className="scene-gallery-grid" aria-live="polite">
          {visibleScenes.map((scene) => {
            return (
              <article className={`scene-gallery-card ${scene.availability}`} key={scene.id}>
                <div className="scene-card-header">
                  <span className={`scene-line-icon scene-tone-${sceneTone(scene.category)}`}><UiIcon name={sceneIcon(scene.category)} size={20} /></span>
                  <div className="scene-card-title-wrap">
                    <h2>{scene.name}</h2>
                    <div className="scene-gallery-tags">{scene.tags.slice(0, 3).map((tag) => <span key={tag}>{tag}</span>)}</div>
                  </div>
                  <div className="scene-gallery-meta">
                    <span className={`availability-badge ${scene.availability}`}>{STATUS_TEXT[scene.availability]}</span>
                  </div>
                </div>
                <p className="scene-card-description">{scene.description}</p>
                <div className="scene-example">
                  <span>示例问题</span>
                  <p>“{scene.exampleQueries[0]}”</p>
                </div>
                {scene.actionHref ? (
                  <Link href={scene.actionHref} className="scene-card-action">{scene.actionLabel}<UiIcon name="send" size={15} /></Link>
                ) : (
                  <span className="scene-card-action disabled" aria-disabled="true">{scene.actionLabel}<span aria-hidden="true">—</span></span>
                )}
              </article>
            );
          })}
          </section>
          <footer className="scene-pagination" aria-label="场景分页">
            <div><span>共 {filteredScenes.length} 条</span><label>每页 <select value={pageSize} onChange={event => setPageSize(Number(event.target.value))}><option value="6">6</option><option value="9">9</option><option value="12">12</option></select> 条</label></div>
            <div className="scene-page-controls"><button type="button" className="secondary-btn" disabled={page <= 1} onClick={() => setPage(current => current - 1)}>上一页</button>{Array.from({ length: totalPages }, (_, index) => index + 1).map(number => <button type="button" key={number} className={number === page ? "active" : ""} aria-current={number === page ? "page" : undefined} onClick={() => setPage(number)}>{number}</button>)}<button type="button" className="secondary-btn" disabled={page >= totalPages} onClick={() => setPage(current => current + 1)}>下一页</button></div>
          </footer>
        </>
      ) : (
        <section className="scene-empty">
          <UiIcon name="search" size={34} />
          <h2>没有找到匹配场景</h2>
          <p>试试更换关键词或查看全部分类。</p>
          <button type="button" onClick={() => { setKeyword(""); selectCategory("全部"); }}>查看全部场景</button>
        </section>
      )}
    </main>
  );
}
