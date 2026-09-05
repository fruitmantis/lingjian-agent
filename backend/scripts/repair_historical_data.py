"""Controlled historical backfill. Prepare is read-only; generate touches a private copy.

Run from the repository root with python -m backend.scripts.repair_historical_data.
No application initialization, case reassignment, rematching, or schema migration.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3


DERIVATIVES = {"demand_profile": "demand_profiles", "project_opportunity": "project_opportunities"}


class RepairConflict(RuntimeError):
    """Abort without including customer data or upstream exception details."""


def connect(path: Path, *, writable: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + ("?mode=rw" if writable else "?mode=ro"), uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {quote(table)} ORDER BY rowid")]


def schema(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(r) for r in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]


def check_integrity(conn: sqlite3.Connection) -> None:
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RepairConflict("数据库完整性检查失败")


def inventory(conn: sqlite3.Connection) -> dict:
    check_integrity(conn)
    if conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] != "9":
        raise RepairConflict("仅支持已核对的 schema v9 数据库")
    tasks = []
    for task in rows(conn, "match_records"):
        missing = []
        for stage, table in DERIVATIVES.items():
            count = conn.execute(f"SELECT count(*) FROM {table} WHERE match_record_id=?", (task["id"],)).fetchone()[0]
            if count > 1:
                raise RepairConflict("存在重复衍生记录，需单独核对")
            if not count:
                missing.append(stage)
        if missing:
            tasks.append({"id": task["id"], "created_at": task["created_at"], "missing": missing,
                          "eligible": task["task_status"] == "ready" and task["archived_at"] is None})
    cases = [dict(r) for r in conn.execute(
        "SELECT c.id,c.partner_id FROM cases c LEFT JOIN partners p ON p.id=c.partner_id WHERE p.id IS NULL")]
    coverage = [dict(r) for r in conn.execute("""
        SELECT p.id, CASE WHEN trim(coalesce(p.ai_profile,''))<>'' THEN 1 ELSE 0 END has_profile,
        (SELECT count(*) FROM cases c WHERE c.partner_id=p.id) cases,
        (SELECT count(*) FROM partner_documents d WHERE d.partner_id=p.id) documents,
        (SELECT count(*) FROM deliverables d JOIN cases c ON c.id=d.case_id WHERE c.partner_id=p.id) deliverables
        FROM partners p WHERE p.status='active' ORDER BY p.id
    """)]
    return {"tasks": tasks, "orphan_cases": cases, "coverage": coverage,
            "model_calls": sum(len(t["missing"]) for t in tasks if t["eligible"]),
            "counts": {t: len(rows(conn, t)) for t in ("partners", "cases", "match_records", *DERIVATIVES.values())}}


def copy_database(source: Path, destination: Path) -> None:
    # Exclusive creation prevents accidentally replacing a live database or earlier backup.
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
        check_integrity(dst)


def prepare(source: Path, work_dir: Path) -> dict:
    work_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    backup = work_dir / "before.db"
    copy_database(source, backup)
    with closing(connect(backup)) as conn:
        plan = inventory(conn)
    plan.update({"format": 1, "source": str(source.resolve()), "backup_sha256": digest(backup)})
    with (work_dir / "plan.json").open("x") as output:
        json.dump(plan, output, ensure_ascii=False, indent=2)
    (work_dir / "plan.json").chmod(0o600)
    copy_database(backup, work_dir / "staged.db")
    return plan


def load_plan(work_dir: Path) -> dict:
    plan = json.loads((work_dir / "plan.json").read_text())
    if plan.get("format") != 1 or digest(work_dir / "before.db") != plan["backup_sha256"]:
        raise RepairConflict("备份或清单发生变化")
    with closing(connect(work_dir / "before.db")) as conn:
        actual = inventory(conn)
    if any(plan.get(key) != value for key, value in actual.items()):
        raise RepairConflict("清单与备份不一致")
    return plan


@contextmanager
def work_lock(work_dir: Path):
    fd = os.open(work_dir / ".maintenance.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RepairConflict("另一维护进程正在使用此副本") from None
        yield
    finally:
        os.close(fd)


def staged_changes(work_dir: Path, *, complete: bool) -> list[tuple[str, dict]]:
    plan = load_plan(work_dir)
    allowed = {(DERIVATIVES[stage], t["id"]) for t in plan["tasks"] if t["eligible"] for stage in t["missing"]}
    changes = []
    with closing(connect(work_dir / "before.db")) as before, closing(connect(work_dir / "staged.db")) as after:
        check_integrity(after)
        if schema(before) != schema(after):
            raise RepairConflict("副本结构发生变化")
        tasks = {t["id"]: t for t in rows(before, "match_records")}
        for entry in before.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            table = entry[0]
            old, new = rows(before, table), rows(after, table)
            if table not in DERIVATIVES.values():
                if old != new:
                    raise RepairConflict("副本修改了本批范围外的数据")
                continue
            old_ids = {r["id"] for r in old}
            if [r for r in new if r["id"] in old_ids] != old:
                raise RepairConflict("副本覆盖了已有衍生记录")
            changes.extend((table, r) for r in new if r["id"] not in old_ids)
        seen = set()
        for table, row in changes:
            key = (table, row["match_record_id"])
            if key not in allowed or key in seen or not row["id"]:
                raise RepairConflict("副本新增记录超出清单或重复")
            seen.add(key)
            if row["requirement_text"] != tasks[row["match_record_id"]]["requirement"]:
                raise RepairConflict("副本需求与原任务不一致")
        if complete and seen != allowed:
            raise RepairConflict("清单中的缺失环节尚未全部生成，禁止部分写入")
        if [tuple(r) for r in before.execute("PRAGMA foreign_key_check")] != [tuple(r) for r in after.execute("PRAGMA foreign_key_check")]:
            raise RepairConflict("副本引入了新的外键异常")
    return changes


def generate_missing(work_dir: Path, max_calls: int) -> dict:
    """Explicit model operation, serial and without automatic retries; only writes staged.db."""
    with work_lock(work_dir):
        return _generate_missing(work_dir, max_calls)


def _generate_missing(work_dir: Path, max_calls: int) -> dict:
    plan = load_plan(work_dir)
    done = {(table, row["match_record_id"]) for table, row in staged_changes(work_dir, complete=False)}
    pending = [(t["id"], stage) for t in plan["tasks"] if t["eligible"] for stage in t["missing"]
               if (DERIVATIVES[stage], t["id"]) not in done]
    if max_calls < len(pending):
        raise RepairConflict("调用额度不足；未发起模型请求")
    if not pending:
        return {"calls": 0, "failed": []}
    with closing(connect(Path(plan["source"]))) as current, closing(connect(work_dir / "before.db")) as before:
        for table in ("model_configs", "model_usage_configs", "capability_tags", "partners"):
            if rows(current, table) != rows(before, table):
                raise RepairConflict("模型或业务资料已变化，需重新准备副本")
        for task_id, _ in pending:
            for table, column in (("match_records", "id"), *((t, "match_record_id") for t in DERIVATIVES.values())):
                sql = f"SELECT * FROM {table} WHERE {column}=? ORDER BY rowid"
                if [tuple(r) for r in current.execute(sql, (task_id,))] != [tuple(r) for r in before.execute(sql, (task_id,))]:
                    raise RepairConflict("任务或已有衍生记录已变化，未发起模型请求")
    # Imported only by explicit generate. No initialize_storage / API startup.
    from backend.app import database
    from backend.app.routers import match

    old_path = database.DATABASE_PATH
    database.DATABASE_PATH = (work_dir / "staged.db").resolve()
    calls, failed = 0, []
    try:
        with closing(connect(database.DATABASE_PATH)) as conn:
            tasks = {t["id"]: t for t in rows(conn, "match_records")}
        for task_id, stage in pending:
            task = tasks[task_id]
            try:
                stored = json.loads(task["recommendations_json"])
                if not isinstance(stored, list) or not stored:
                    raise ValueError("Invalid historical recommendations")
                recs = [match.PartnerRecommendation.model_validate(r) for r in stored]
                calls += 1
                if stage == "demand_profile":
                    match._generate_demand_profile(task_id, task["requirement"], recs, task["created_at"], strict=True)
                elif not match._extract_project_opportunity(task["requirement"], task_id, recs, strict=True):
                    raise ValueError("Opportunity generation failed")
            except Exception:
                failed.append({"id": task_id, "stage": stage})
                # Stop at first failure to bound cost; successful stages remain reusable.
                break
    finally:
        database.DATABASE_PATH = old_path
    staged_changes(work_dir, complete=False)
    return {"calls": calls, "failed": failed}


def transfer(work_dir: Path, target: Path, *, rollback: bool = False) -> int:
    """Atomic row-level apply/undo. Never restore a whole file or overwrite existing rows."""
    if target.resolve() in {(work_dir / name).resolve() for name in ("before.db", "staged.db")}:
        raise RepairConflict("禁止将备份或生成副本用作写入目标")
    with work_lock(work_dir):
        return _transfer(work_dir, target, rollback=rollback)


def _transfer(work_dir: Path, target: Path, *, rollback: bool) -> int:
    changes = staged_changes(work_dir, complete=True)
    with closing(connect(work_dir / "before.db")) as before, closing(connect(target, writable=True)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if schema(conn) != schema(before):
                raise RepairConflict("目标库结构已变化，需重新核对")
            violations = [tuple(r) for r in conn.execute("PRAGMA foreign_key_check")]
            operations = []
            for table, row in changes:
                task_id = row["match_record_id"]
                old_task = dict(before.execute("SELECT * FROM match_records WHERE id=?", (task_id,)).fetchone())
                task = conn.execute("SELECT * FROM match_records WHERE id=?", (task_id,)).fetchone()
                if task is None or dict(task) != old_task:
                    raise RepairConflict("任务已被修改，需重新核对")
                existing = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row["id"],)).fetchone()
                linked = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE match_record_id=?", (task_id,))]
                if existing is not None and (dict(existing) != row or linked != [row]):
                    raise RepairConflict("补齐记录已被修改或出现重复，禁止覆盖")
                if rollback:
                    if existing is not None:
                        operations.append((table, row))
                elif existing is None:
                    if linked:
                        raise RepairConflict("缺失环节已由其他操作补齐，禁止覆盖")
                    # The other derivative contributes to generation context and must stay unchanged.
                    for other in DERIVATIVES.values():
                        original = [dict(r) for r in before.execute(f"SELECT * FROM {other} WHERE match_record_id=?", (task_id,))]
                        current = [dict(r) for r in conn.execute(f"SELECT * FROM {other} WHERE match_record_id=?", (task_id,))]
                        staged_for_task = [r for t, r in changes if t == other and r["match_record_id"] == task_id]
                        if original != current and current != staged_for_task:
                            raise RepairConflict("已有衍生记录已变化，需重新核对")
                    operations.append((table, row))
            if operations and not rollback:
                for context_table in ("partners", "capability_tags"):
                    if rows(conn, context_table) != rows(before, context_table):
                        raise RepairConflict("伙伴或标签资料已变化，需重新核对")
            for table, row in operations:
                if rollback:
                    conn.execute(f"DELETE FROM {table} WHERE id=?", (row["id"],))
                else:
                    columns = ",".join(quote(k) for k in row)
                    placeholders = ",".join("?" for _ in row)
                    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(row.values()))
            check_integrity(conn)
            if violations != [tuple(r) for r in conn.execute("PRAGMA foreign_key_check")]:
                raise RepairConflict("操作改变了外键异常清单")
            conn.commit()
            return len(operations)
        except Exception:
            conn.rollback()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "generate", "check", "apply", "rollback"))
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--max-calls", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.command in {"prepare", "apply", "rollback"} and args.database is None:
            parser.error("该命令必须显式指定 --database")
        if args.command == "prepare":
            plan = prepare(args.database, args.work_dir)
            result = {"tasks": len(plan["tasks"]), "max_model_calls": plan["model_calls"], "orphan_cases": len(plan["orphan_cases"])}
        elif args.command == "generate":
            result = generate_missing(args.work_dir, args.max_calls)
        elif args.command == "check":
            result = {"staged_rows": len(staged_changes(args.work_dir, complete=True))}
        else:
            result = {"changed_rows": transfer(args.work_dir, args.database, rollback=args.command == "rollback")}
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("failed") else 0
    except RepairConflict as error:
        print(str(error))
        return 1
    except Exception:
        print("维护操作未完成；未输出业务数据或底层异常。请检查隔离清单、备份及冲突状态。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
