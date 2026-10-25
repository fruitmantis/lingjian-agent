"""LLM-based partner matching router with match record history."""

from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
import json
import math
import re
import uuid
from time import perf_counter
from typing import Literal
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import field_validator, BaseModel, Field

from backend.business import matching
from .. import match_understanding as understanding
from .. import partner_match_context as match_context
from ..model_resolver import pinned_configuration
from .. import development_model, task_progress, agent_settings
from ..error_diagnostics import diagnostic_scope, bind_context, record_error
from ..task_failures import failure, public_failures, PublicTaskError, MatchInputBudgetError
from ..opportunity_extraction import normalize_opportunity
from ..ai_client import model_error_message
from ..model_resolver import ModelConfigurationError
from ..business_taxonomy import canonical, classify, project_partner, taxonomy_prompt
from ..database import get_db, recover_stale_tasks
from ..development_lifecycle import fingerprint
from ..model_timeout_settings import get_settings
from ..ai_client import last_retry_count, reset_retry_count
from ..auth import require_active_user, require_admin, ensure_account_active
from .demand import calculate_opportunity_completeness


router = APIRouter(prefix="/agent", tags=["agent"])
admin_router = APIRouter(prefix="/admin", tags=["admin-tasks"], dependencies=[Depends(require_admin)])

MAX_RECOMMENDATIONS = 5
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="partner-match")

_P_COLS = "id, name, intro, capabilities, service_areas, industries, ai_profile, created_at"
_CASE_COLS = "id, partner_id, title, description, created_at"


def _to_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


class MatchRequest(BaseModel):
    modelConfigId: str | None = Field(default=None,min_length=1,max_length=128)
    requirement: str = Field(..., min_length=1, description="项目需求描述")


class TaskCreateRequest(MatchRequest):
    requirement: str = Field(..., min_length=1, max_length=2000, description="项目需求描述")
    requestId: uuid.UUID


class TaskAccepted(BaseModel):
    runId: str | None = None
    recordId: str
    taskStatus: str


class PartnerRecommendation(BaseModel):
    partnerId: str
    partnerName: str
    matchScore: str
    matchedCapabilities: str
    @field_validator("matchedIndustries", "matchedRegions", mode="before")
    @classmethod
    def standard_match_labels(cls, value, info):
        return canonical(value,"industry" if info.field_name=="matchedIndustries" else "region") or ""

    matchedIndustries: str
    matchedRegions: str
    recommendationReason: str
    evidenceCases: str
    evidenceDeliverables: str
    riskNotes: str


class MatchResponse(BaseModel):
    requirement: str
    recommendations: list[PartnerRecommendation]
    recordId: str | None = None
    taskStatus: str = "ready"


class MatchRecordSummary(BaseModel):
    planPresentation: dict | None = None
    task_type: Literal["partner_match", "development_plan"] = "partner_match"
    id: str
    requirement: str
    topPartner: str
    partnerCount: int
    createdAt: str
    archivedAt: str | None
    ownerName: str | None
    department: str | None
    completenessScore: float | None
    taskStatus: str
    lastErrorStage: str | None
    failureDetails: list[dict] = Field(default_factory=list)


class TaskListResponse(BaseModel):
    items: list[MatchRecordSummary]
    page: int
    pageSize: int
    total: int
    totalPages: int


class MatchRecordDetail(BaseModel):
    modelSelection: dict | None = None
    progress: dict | None = None
    understanding: dict | None = None
    scopeMessage: str | None = None
    answer: str = ""
    planPresentation: dict | None = None
    task_type: Literal["partner_match", "development_plan"] = "partner_match"
    id: str
    requirement: str
    recommendations: list[PartnerRecommendation]
    createdAt: str
    createdBy: str | None
    archivedAt: str | None
    demandProfile: dict | None
    opportunity: dict | None
    taskStatus: str
    lastErrorStage: str | None
    failureDetails: list[dict] = Field(default_factory=list)


def _demand_profile_dict(row) -> dict | None:
    if row is None:
        return None
    return {
        "classification_pending": {"industryTags":classify(row["industry_tags"],"industry")[1],"regionTags":classify(row["region_tags"],"region")[1]},
        "id": row["id"], "industryTags": canonical(row["industry_tags"],"industry"), "capabilityTags": row["capability_tags"],
        "deliveryTypeTags": row["delivery_type_tags"], "regionTags": canonical(row["region_tags"],"region"),
        "complexityLevel": row["complexity_level"], "urgencyLevel": row["urgency_level"],
        "projectKeywords": row["project_keywords"], "matchedPartnerCount": row["matched_partner_count"],
        "topPartnerNames": row["top_partner_names"], "supplyStatus": row["supply_status"],
        "gapAnalysis": row["gap_analysis"], "createdAt": row["created_at"],
    }


def _opportunity_dict(row) -> dict | None:
    if row is None:
        return None
    mapping = {
        "id": "id", "customerName": "customer_name", "projectName": "project_name", "industry": "industry",
        "region": "region", "projectStage": "project_stage", "businessNeeds": "business_needs",
        "technicalNeeds": "technical_needs", "deliveryNeeds": "delivery_needs",
        "qualificationRequirements": "qualification_requirements", "caseRequirements": "case_requirements",
        "onsiteRequirement": "onsite_requirement", "timelineRequirement": "timeline_requirement",
        "cloudPlatformPreference": "cloud_platform_preference", "matchedCapabilityTags": "matched_capability_tags",
        "unmatchedCapabilitySignals": "unmatched_capability_signals", "recommendedPartnerNames": "recommended_partner_names",
        "supplyStatus": "supply_status", "completenessScore": "completeness_score", "missingFields": "missing_fields",
        "followUpQuestions": "follow_up_questions", "createdAt": "created_at", "updatedAt": "updated_at",
    }
    result={key: row[column] for key, column in mapping.items()}
    result["classification_pending"]={"industry":classify(result["industry"],"industry")[1],"region":classify(result["region"],"region")[1]}
    result["industry"]=canonical(result["industry"],"industry")
    result["region"]=canonical(result["region"],"region")
    return result


def _query_tasks(
    *, owner_user_id: str | None, archived: bool, keyword: str | None,
    owner_keyword: str | None, task_status: str | None, page: int, page_size: int,
    before_created_at: str | None = None, before_id: str | None = None,
    ids: list[str] | None = None, task_type: str | None = None,
) -> TaskListResponse:
    recover_stale_tasks(owner_user_id=owner_user_id)
    from ..development_lifecycle import recover,PLAN_COLUMNS
    recover(owner_user_id=owner_user_id)
    cte = """WITH unified AS (
        SELECT id, owner_user_id, requirement, recommendations_json, created_at, archived_at, task_status, last_error_stage, last_error_details AS failure_details, 'partner_match' AS task_type FROM match_records
        UNION ALL
        SELECT p.id,p.owner_user_id,(q.payload_json::jsonb #>> '{development_goal}'),CASE WHEN p.target_partner_id IS NULL THEN '[]' ELSE CAST(jsonb_build_array(jsonb_build_object('partnerName',COALESCE(t.name,''))) AS TEXT) END,p.created_at,p.archived_at,
        CASE WHEN r.status IN ('pending','running') THEN 'matching' WHEN p.current_version_id IS NOT NULL OR r.status='ready' THEN 'ready' ELSE 'failed' END,r.error_stage,r.safe_error_message,'development_plan'
        FROM development_plans p JOIN development_requests q ON q.id=p.request_id LEFT JOIN partners t ON t.id=p.target_partner_id
        LEFT JOIN development_runs r ON r.id=COALESCE(p.active_run_id,(SELECT id FROM development_runs WHERE plan_id=p.id ORDER BY created_at DESC,id DESC LIMIT 1))
    ) """
    conditions = ["mr.archived_at IS NOT NULL" if archived else "mr.archived_at IS NULL"]
    params: list[object] = []
    if task_type:
        conditions.append("mr.task_type = ?"); params.append(task_type)
    if owner_user_id:
        conditions.append("mr.owner_user_id = ?"); params.append(owner_user_id)
    if keyword:
        conditions.append("mr.requirement ILIKE ?"); params.append(f"%{keyword}%")
    if owner_keyword:
        conditions.append("(u.username ILIKE ? OR u.display_name ILIKE ? OR u.department ILIKE ?)")
        params.extend([f"%{owner_keyword}%", f"%{owner_keyword}%", f"%{owner_keyword}%"])
    if task_status:
        conditions.append("mr.task_status = ?"); params.append(task_status)
    if before_created_at and before_id:
        conditions.append("(mr.created_at < ? OR (mr.created_at = ? AND mr.id < ?))")
        params.extend([before_created_at, before_created_at, before_id])
    if ids:
        conditions.append(f"mr.id IN ({','.join('?' for _ in ids)})")
        params.extend(ids)
    where = " WHERE " + " AND ".join(conditions)
    with get_db() as conn:
        total = conn.execute(
            cte + f"SELECT COUNT(*) FROM unified mr LEFT JOIN users u ON u.id = mr.owner_user_id{where}", params,
        ).fetchone()[0]
        rows = conn.execute(
            cte + f"""SELECT mr.task_type, mr.id, mr.requirement, mr.recommendations_json, mr.created_at, mr.archived_at,
                       mr.task_status, mr.last_error_stage, mr.failure_details, CASE WHEN u.status='deleted' THEN '已删除用户' ELSE u.display_name END AS owner_name, u.department,
                       (SELECT po.completeness_score FROM project_opportunities po
                        WHERE po.match_record_id = mr.id ORDER BY po.created_at DESC LIMIT 1) AS completeness_score
                FROM unified mr
                LEFT JOIN users u ON u.id = mr.owner_user_id
                {where} ORDER BY mr.created_at DESC, mr.id DESC LIMIT ? OFFSET ?""",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    items = []
    for row in rows:
        requirement=row['requirement']
        plan_presentation=None
        if row['task_type']=='development_plan':
            from ..development_views import protected,presentation
            with get_db() as conn:
                conn.begin_read()
                plan=conn.execute(f'SELECT {PLAN_COLUMNS} FROM development_plans WHERE id=?',(row['id'],)).fetchone()
                plan_presentation=presentation(conn,plan)
                version=conn.execute('SELECT v.* FROM development_versions v JOIN development_plans p ON p.current_version_id=v.id WHERE p.id=?',(row['id'],)).fetchone()
                if version and protected(conn,version):requirement='发展方案（来源授权已变化）'
        recs = json.loads(row["recommendations_json"])
        top = recs[0]["partnerName"] if recs else "无"
        items.append(MatchRecordSummary(
            planPresentation=plan_presentation, task_type=row["task_type"], id=row["id"], requirement=requirement, topPartner=top, partnerCount=len(recs),
            createdAt=row["created_at"], archivedAt=row["archived_at"], ownerName=row["owner_name"],
            department=row["department"], completenessScore=row["completeness_score"],
            taskStatus=row["task_status"], lastErrorStage=row["last_error_stage"],
            failureDetails=public_failures(row["last_error_stage"],row["failure_details"]) if row["task_status"] in ("partial","failed","interrupted") else [],
        ))
    return TaskListResponse(
        items=items, page=page, pageSize=page_size, total=total,
        totalPages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/tasks", response_model=TaskListResponse)
def list_match_records(
    task_type: Literal["partner_match", "development_plan"] | None = None,    archive_status: str = Query("active", alias="status", pattern="^(active|archived)$"),
    keyword: str | None = None,
    task_status: str | None = Query(None, alias="taskStatus", pattern="^(matching|enriching|ready|partial|failed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    before_created_at: str | None = Query(None, alias="beforeCreatedAt", max_length=100),
    before_id: str | None = Query(None, alias="beforeId", max_length=128),
    ids: list[str] | None = Query(None),
    user: dict = Depends(require_active_user),
) -> TaskListResponse:
    if bool(before_created_at) != bool(before_id) or (ids is not None and (len(ids) > 100 or any(len(i) > 128 for i in ids))):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务查询参数无效")
    return _query_tasks(
        owner_user_id=user["id"], archived=archive_status == "archived", keyword=keyword,
        owner_keyword=None, task_status=task_status, page=page, page_size=page_size, task_type=task_type,
        before_created_at=before_created_at, before_id=before_id, ids=ids,
    )


@admin_router.get("/tasks", response_model=TaskListResponse)
def list_admin_tasks(
    task_type: Literal["partner_match", "development_plan"] | None = None,    archive_status: str = Query("active", alias="status", pattern="^(active|archived)$"),
    keyword: str | None = None,
    owner: str | None = None,
    task_status: str | None = Query(None, alias="taskStatus", pattern="^(matching|enriching|ready|partial|failed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    _: dict = Depends(require_admin),
) -> TaskListResponse:
    return _query_tasks(
        owner_user_id=None, archived=archive_status == "archived", keyword=keyword,
        owner_keyword=owner, task_status=task_status, page=page, page_size=page_size, task_type=task_type,
    )


@admin_router.get("/dashboard")
def get_admin_dashboard(_: dict = Depends(require_admin)) -> dict:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with get_db() as conn:
        counts = {row['task_type']: row for row in conn.execute("""
            SELECT task_type, COUNT(*) AS total,
                   SUM(CASE WHEN substr(created_at, 1, 7) = ? THEN 1 ELSE 0 END) AS month_total
            FROM (
                SELECT 'partner_match' AS task_type, created_at FROM match_records
                UNION ALL
                SELECT 'development_plan', created_at FROM development_plans
            ) GROUP BY task_type
        """, (month,))}
        matching = counts.get('partner_match', {'total': 0, 'month_total': 0})
        development = counts.get('development_plan', {'total': 0, 'month_total': 0})
        return {
            "users": conn.execute("SELECT COUNT(*) FROM users WHERE status <> 'deleted'").fetchone()[0],
            "disabledUsers": conn.execute("SELECT COUNT(*) FROM users WHERE status = 'disabled'").fetchone()[0],
            "partners": conn.execute("SELECT COUNT(*) FROM partners WHERE status = 'active'").fetchone()[0],
            "partnersWithoutProfile": conn.execute("SELECT COUNT(*) FROM partners WHERE status = 'active' AND (ai_profile IS NULL OR ai_profile = '')").fetchone()[0],
            "tasks": matching['total'] + development['total'],
            "monthTasks": matching['month_total'] + development['month_total'],
            "partnerMatchTasks": matching['total'],
            "developmentTasks": development['total'],
            "monthPartnerMatchTasks": matching['month_total'],
            "monthDevelopmentTasks": development['month_total'],
            "opportunities": conn.execute("SELECT COUNT(*) FROM project_opportunities").fetchone()[0],
            "gapDemands": conn.execute("SELECT COUNT(*) FROM demand_profiles WHERE supply_status = 'gap'").fetchone()[0],
            "pendingSuggestions": conn.execute("SELECT COUNT(*) FROM capability_tag_suggestions WHERE status = 'pending'").fetchone()[0],
        }


def _recover_accessible_task(record_id: str, user: dict) -> None:
    """Check ownership before recovery, and scope the write to that owner."""
    with get_db() as conn:
        task = conn.execute(
            "SELECT owner_user_id FROM match_records WHERE id = ?", (record_id,),
        ).fetchone()
    if task is None or (task["owner_user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="推荐任务不存在")
    recover_stale_tasks(record_id=record_id, owner_user_id=task["owner_user_id"])


@router.get("/tasks/{record_id}", response_model=MatchRecordDetail)
def get_match_record(record_id: str, user: dict = Depends(require_active_user)) -> MatchRecordDetail:
    from .. import development_lifecycle as life
    with get_db() as conn:
        exists = conn.execute('SELECT id FROM development_plans WHERE id=?',(record_id,)).fetchone()
        if exists:
            plan=life.authorize(conn,record_id,user)
            owner=plan['owner_user_id']
    if exists:
        summary=_query_tasks(owner_user_id=owner,archived=bool(plan['archived_at']),keyword=None,owner_keyword=None,task_status=None,page=1,page_size=1,ids=[record_id]).items[0]
        return MatchRecordDetail(planPresentation=summary.planPresentation,task_type='development_plan',id=record_id,requirement=summary.requirement,recommendations=[],createdAt=summary.createdAt,createdBy=summary.ownerName,archivedAt=summary.archivedAt,demandProfile=None,opportunity=None,taskStatus=summary.taskStatus,lastErrorStage=summary.lastErrorStage,failureDetails=summary.failureDetails)
    _recover_accessible_task(record_id, user)
    with get_db() as conn:
        row = conn.execute("""SELECT mr.id, mr.requirement, mr.recommendations_json, mr.created_at, mr.archived_at,
                                     mr.task_status, mr.last_error_stage, mr.last_error_details,
                                     mr.owner_user_id, CASE WHEN u.status='deleted' THEN '已删除用户' ELSE u.display_name END AS owner_name
                              FROM match_records mr LEFT JOIN users u ON u.id = mr.owner_user_id
                              WHERE mr.id = ?""", (record_id,)).fetchone()
        if row is not None and row["owner_user_id"] != user["id"] and user["role"] != "admin":
            row = None
        demand_profile = conn.execute("SELECT * FROM demand_profiles WHERE match_record_id = ? ORDER BY created_at DESC LIMIT 1", (record_id,)).fetchone() if row else None
        opportunity = conn.execute("SELECT * FROM project_opportunities WHERE match_record_id = ? ORDER BY created_at DESC LIMIT 1", (record_id,)).fetchone() if row else None
        snapshot=understanding.load(conn,record_id) if row else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="记录不存在")
    recs = json.loads(row["recommendations_json"])
    from backend.business.common import historical_match_answer
    answer=historical_match_answer((snapshot or {}).get("visible_answer",""),(snapshot or {}).get('format_version'))
    # Resolve saved, actually sent aliases for display only; retain the original snapshot.
    with get_db() as conn:
        aliases=_public_source_aliases(conn,(snapshot or {}).get('detail_rows',[]))
    answer=_display_source_aliases(answer,aliases)
    recs=[{k:_display_source_aliases(v,aliases) if k in ('recommendationReason','riskNotes') and isinstance(v,str) else v for k,v in rec.items()} for rec in recs]
    public_demand=_demand_profile_dict(demand_profile)
    if public_demand:public_demand['gapAnalysis']=_display_source_aliases(public_demand['gapAnalysis'],aliases)
    if user["role"]!="admin":
        from ..profile_sources import redact_sources,hidden_labels,sources
        labels=[]
        with get_db() as conn:
            referenced={rec['partnerId'] for rec in recs}|{ref['partnerId'] for ref in (snapshot or {}).get('outcome',{}).get('analysisRefs',[])}
            for partner_id in referenced:
                labels.extend(hidden_labels(sources(conn,partner_id)))
        answer=redact_sources(answer,labels)
        recs=[{k:redact_sources(v,labels) if k in ("recommendationReason","riskNotes","evidenceCases","evidenceDeliverables") and isinstance(v,str) else v for k,v in rec.items()} for rec in recs]
    return MatchRecordDetail(modelSelection=agent_settings.public_selection((snapshot or {}).get("agent_execution")),progress=(snapshot or {}).get("progress"),understanding=(snapshot or {}).get("understanding",{}).get("facts") if (snapshot or {}).get("understanding",{}).get("in_scope") else None,scopeMessage=(snapshot or {}).get("scope_message"),answer=answer,id=row["id"], requirement=row["requirement"], recommendations=recs, createdAt=row["created_at"], createdBy=row["owner_name"], archivedAt=row["archived_at"], demandProfile=public_demand, opportunity=_opportunity_dict(opportunity), taskStatus=row["task_status"], lastErrorStage=row["last_error_stage"],failureDetails=public_failures(row["last_error_stage"],row["last_error_details"]) if row["task_status"] in ("partial","failed") else [])


def _model_value(item: dict, field: str):
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()
    return item.get(field, item.get(snake))


def _reference_tokens(value) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,，;；\n]", value) if part.strip()]
    if isinstance(value, list) and all(isinstance(part, str) for part in value):
        return [part.strip() for part in value if part.strip()]
    return []


def _verified_references(value, rows: list[dict], label_field: str) -> list[dict]:
    """Accept IDs or exact, unambiguous legacy labels within this partner only."""
    by_id = {row["id"]: row for row in rows}
    by_label: dict[str, list[dict]] = {}
    for row in rows:
        by_label.setdefault(row[label_field], []).append(row)
    tokens = ([value.strip()] if isinstance(value, str) and value.strip() in (by_id.keys() | by_label.keys())
              else _reference_tokens(value))
    selected: dict[str, dict] = {}
    for token in tokens:
        row = by_id.get(token)
        matches = by_label.get(token, [])
        if row is None and len(matches) == 1:
            row = matches[0]
        if row:
            selected.setdefault(row["id"], row)
    return list(selected.values())


def _validated_recommendations(items: list, partners: list[dict], cases: dict, deliverables: dict, rejections: list[str] | None = None) -> list[PartnerRecommendation]:
    by_id = {partner["id"]: partner for partner in partners}
    by_name: dict[str, list[dict]] = {}
    for partner in partners:
        by_name.setdefault(partner["name"], []).append(partner)
    valid: list[PartnerRecommendation] = []
    rejected = rejections if rejections is not None else []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            rejected.append(f'推荐第 {index + 1} 项不是对象')
            continue
        partner_id = _model_value(item, "partnerId")
        partner_name = _model_value(item, "partnerName")
        if partner_id:
            partner = by_id.get(partner_id) if isinstance(partner_id, str) else None
            if partner and partner_name and partner_name != partner["name"]:
                rejected.append(f'推荐第 {index + 1} 项的 partnerId 与 partnerName 不一致')
                continue
        else:
            names = by_name.get(partner_name, []) if isinstance(partner_name, str) else []
            partner = names[0] if len(names) == 1 else None
        if partner is None:
            rejected.append(f'推荐第 {index + 1} 项无法对应启用的候选伙伴（partnerId/partnerName）')
            continue
        score_value = _model_value(item, "matchScore")
        if isinstance(score_value, bool) or not isinstance(score_value, (str, float, int)):
            rejected.append(f'推荐第 {index + 1} 项 matchScore 类型无效')
            continue
        try:
            score = float(score_value)
        except (TypeError, ValueError, OverflowError):
            rejected.append(f'推荐第 {index + 1} 项 matchScore 无法解析为数字')
            continue
        reason = _model_value(item, "recommendationReason")
        if not math.isfinite(score) or not 0 <= score <= 100:
            rejected.append(f'推荐第 {index + 1} 项 matchScore 必须是 0～100 的有限数字')
            continue
        if not isinstance(reason, str) or not reason.strip():
            rejected.append(f'推荐第 {index + 1} 项 recommendationReason 为空或不是文本')
            continue
        reason = reason.strip()
        pid = partner["id"]
        matched = {}
        for field, column in (("matchedCapabilities", "capabilities"), ("matchedIndustries", "industries"), ("matchedRegions", "service_areas")):
            proposed = _reference_tokens(_model_value(item, field))
            if column in ("industries", "service_areas"):
                kind = "industry" if column == "industries" else "region"
                proposed = _reference_tokens(canonical(proposed,kind))
                available = set(_reference_tokens(canonical(partner.get(column),kind)))
            else:
                available = set(_reference_tokens(partner.get(column)))
            verified = list(dict.fromkeys(token for token in proposed if token in available))
            matched[field] = ", ".join(verified)
        case_rows = _verified_references(_model_value(item, "evidenceCases"), cases.get(pid, []), "title")
        deliverable_rows = _verified_references(_model_value(item, "evidenceDeliverables"), deliverables.get(pid, []), "filename")
        if (not _references_valid(_model_value(item, "evidenceCases"), cases.get(pid, []), "title", pid)
                or not _references_valid(_model_value(item, "evidenceDeliverables"), deliverables.get(pid, []), "filename", pid,
                                         owned_cases=cases.get(pid, []))):
            rejected.append(f'推荐第 {index + 1} 项含未发送或不属于本伙伴的案例/交付物引用')
            continue

        risk = _model_value(item, "riskNotes")
        risk = risk.strip() if isinstance(risk, str) else ""
        valid.append(PartnerRecommendation(
            partnerId=pid, partnerName=partner["name"], matchScore=f"{score:g}",
            **matched, recommendationReason=reason.strip(),
            evidenceCases="；".join(row["title"] for row in case_rows),
            evidenceDeliverables="；".join(f"{row['filename']}（案例：{row['case_title']}）" for row in deliverable_rows),
            riskNotes=risk,
        ))
    # Rank validated candidates, deduplicate by stable ID, and enforce the public limit.
    selected: dict[str, PartnerRecommendation] = {}
    for rec in sorted(valid, key=lambda rec: float(rec.matchScore), reverse=True):
        selected.setdefault(rec.partnerId, rec)
    return list(selected.values())[:MAX_RECOMMENDATIONS]


def _references_valid(value, rows, label_field, partner_id, *, owned_cases=None, ids_only=False):
    if ids_only and (not isinstance(value,list) or any(not isinstance(ref,str) for ref in value)):
        return False
    tokens = _reference_tokens(value)
    allowed = []
    for row in rows:
        if owned_cases is None:
            if row.get('partner_id') != partner_id:
                continue
        elif row.get('case_id') not in {c['id'] for c in owned_cases if c.get('partner_id') == partner_id}:
            continue
        allowed.append(row)
    if ids_only:
        return all(token in {row["id"] for row in allowed} for token in tokens)
    # Exact legacy labels are restricted to existing history compatibility.
    if isinstance(value, str) and any(value.strip() in (r['id'],r.get(label_field)) for r in allowed):
        tokens = [value.strip()]
    return all(len(_verified_references([token],allowed,label_field)) == 1 for token in tokens)




def _source_assessment(item, row, requirement="", facts=None):
    """Resolve only IDs in the actual sent map; professional judgment stays model-owned."""
    if not row:
        return None
    partner,context,cases,deliverables=row
    pid=partner['id']; mapping=context.get('_sourceMap',{})
    passages={p['source']:p['text'] for p in context.get('profilePassages',[])}
    quotes=[]
    refs=item.get('profileEvidence')
    if not isinstance(refs,list) or any(not isinstance(ref,str) for ref in refs):
        return None
    for ref in refs:
        entry=mapping.get(ref)
        if (not entry or entry.get('partnerId')!=pid or not entry.get('text')
                or passages.get(ref)!=entry['text'] or entry['end']-entry['start']!=len(entry['text'])):
            return None
        quotes.append({'source':ref,'quote':entry['text']})
    if not _references_valid(item.get('evidenceCases'),cases,'title',pid,ids_only=True):
        return None
    if not _references_valid(item.get('evidenceDeliverables'),deliverables,'filename',pid,owned_cases=cases,ids_only=True):
        return None
    kind=item.get('evidenceType','current_capability')
    if kind not in ('current_capability','delivered_project','planning_only','unrelated'):
        return None
    item['_resolvedProfileEvidence']=quotes
    return kind


def _same_generated_card(item, rec):
    if not isinstance(item,dict) or not isinstance(item.get('recommendationReason'),str):
        return False
    identity = item.get('partnerId') == rec.partnerId or (
        not item.get('partnerId') and item.get('partnerName') == rec.partnerName)
    try:
        return identity and rec.recommendationReason in (item['recommendationReason'].strip(),item.get('_public_recommendation_reason')) and float(item.get('matchScore')) == float(rec.matchScore)
    except (TypeError,ValueError,OverflowError):
        return False


def _current_reference_valid(conn, item, row):
    from ..profile_sources import sources,stamp,TABLE
    if not row or _source_assessment(item,row) is None:
        return False
    partner,context,cases,files=row; pid=partner['id']
    current=conn.execute("SELECT * FROM partners WHERE id=? AND status='active'",(pid,)).fetchone()
    if not current:
        return False
    source_index={(s['kind'],s['id']):s for s in sources(conn,pid)}
    for ref in item['profileEvidence']:
        entry=context['_sourceMap'][ref]
        kind,sid=entry['sourceRef'].split(':',1)
        if kind=='partner':
            field=entry['path'].lstrip('/')
            value=current[field] or ''
        else:
            source=source_index.get((kind,sid))
            if not source or stamp(source)!=entry['source_version'] or source['processing_status']!='ready':
                return False
            contribution=conn.execute(f'SELECT state,source_fingerprint,sections_json FROM {TABLE} WHERE partner_id=? AND source_kind=? AND source_id=?',(pid,kind,sid)).fetchone()
            if not contribution or contribution['state']!='ready' or contribution['source_fingerprint']!=entry['source_version']:
                return False
            if entry['path']=='/text':
                value=source['text']
            else:
                try:
                    value=json.loads(contribution['sections_json'])
                    for component in entry['path'].strip('/').split('/'):
                        value=value[int(component)] if isinstance(value,list) else value[component]
                except (ValueError,KeyError,IndexError,TypeError):
                    return False
        if not isinstance(value,str) or value[entry['start']:entry['end']]!=entry['text']:
            return False
    for case_id in item['evidenceCases']:
        old=next(c for c in cases if c['id']==case_id)
        actual=conn.execute('SELECT * FROM cases WHERE id=? AND partner_id=? AND visible=1',(case_id,pid)).fetchone()
        if not actual or any(actual[key]!=old[key] for key in ('title','description','created_at') if key in old):
            return False
    for file_id in item['evidenceDeliverables']:
        old=next(f for f in files if f['id']==file_id)
        actual=conn.execute('SELECT d.*,c.partner_id,c.visible FROM deliverables d JOIN cases c ON c.id=d.case_id WHERE d.id=? AND c.partner_id=? AND c.visible=1',(file_id,pid)).fetchone()
        if not actual or any(actual[key]!=old[key] for key in ('case_id','filename','file_path','processed_at') if key in old):
            return False
    return True


def _public_source_aliases(conn, rows):
    """Resolve only the actual sent alias map to owned, currently public source labels."""
    from ..profile_sources import sources,redact_sources,stamp
    aliases={}
    for partner,context,cases,files in rows:
        pid=partner['id']
        current={(source['kind'],source['id']):source for source in sources(conn,pid)}
        owned_cases={case['id'] for case in cases if case.get('partner_id')==pid}
        public_labels={('case',case['id']):case['title'] for case in cases if case['id'] in owned_cases}
        public_labels.update({('attachment',file['id']):file['filename'] for file in files if file.get('case_id') in owned_cases})
        passages={passage['source']:passage['text'] for passage in context.get('profilePassages',[])}
        for alias,entry in context.get('_sourceMap',{}).items():
            if not alias or entry.get('partnerId')!=pid or not entry.get('text') or passages.get(alias)!=entry['text']:
                continue
            kind,separator,sid=entry.get('sourceRef','').partition(':')
            if not separator:continue
            source=current.get((kind,sid))
            if kind=='partner' and sid==pid:
                label=partner['name']+'伙伴信息'
            elif (source and source.get('visible') and entry.get('source_version')==stamp(source)
                  and public_labels.get((kind,sid))==source['label']):
                label=redact_sources(source['label'])
            else:
                label='[未展示资料]'
            aliases[alias]=label
    return aliases


def _display_source_aliases(text, aliases):
    """Literal reference projection; unknown codes and surrounding business facts stay intact."""
    if not text or not aliases:return text
    keys=sorted(aliases,key=len,reverse=True)
    def identifier(char):return char.isascii() and (char.isalnum() or char in '_-')
    parts=[];position=0
    while position<len(text):
        alias=next((key for key in keys if text.startswith(key,position)
                    and (position==0 or not identifier(text[position-1]))
                    and (position+len(key)==len(text) or not identifier(text[position+len(key)]))),None)
        if alias:
            parts.append(aliases[alias]);position+=len(alias)
        else:
            parts.append(text[position]);position+=1
    return ''.join(parts)


def _validated_outcome(recs, output, rejected, rows, *, requirement="", facts=None, catalog_incomplete=False, connection=None):
    from ..profile_sources import redact_sources,hidden_labels,sources
    by_id={row[0]['id']:row for row in rows}
    accepted,plans=[],[]; adopted={}; accepted_items={}; unsupported=False
    with (nullcontext(connection) if connection is not None else get_db()) as conn:
        for rec in recs:
            item=next((item for item in output.get('recommendations',[]) if _same_generated_card(item,rec)),None)
            row=by_id.get(rec.partnerId)
            if not item or not _current_reference_valid(conn,item,row):
                unsupported=True
                continue
            kind=_source_assessment(item,row)
            if kind=='planning_only':
                plans.append(rec.partnerName)
            elif kind!='unrelated':
                accepted.append(rec)
                accepted_items[rec.partnerId]=item
                adopted[rec.partnerId]={key:item[key] for key in ('partnerId','profileEvidence','evidenceCases','evidenceDeliverables')}
                adopted[rec.partnerId]['resolvedProfileEvidence']=item['_resolvedProfileEvidence']
        # Planning units are retained independently when formal cards are rechecked at save.
        for item in output.get('recommendations',[]):
            row=by_id.get(item.get('partnerId'))
            if item.get('evidenceType')=='planning_only' and _current_reference_valid(conn,item,row):
                name=row[0]['name']
                if name not in plans:plans.append(name)
        analysis_valid=bool(output.get('_analysis_shape_valid'))
        refs=output.get('analysisRefs',[])
        if analysis_valid:
            analysis_valid=all(_current_reference_valid(conn,ref,by_id.get(ref['partnerId'])) for ref in refs)
        allowed_names={rec.partnerName for rec in accepted}|set(plans)
        if analysis_valid:
            allowed_names.update(by_id[ref['partnerId']][0]['name'] for ref in refs)
        labels=[]
        for row in rows:
            labels.extend(hidden_labels(sources(conn,row[0]['id'])))
        known_names={r['name'] for r in conn.execute('SELECT name FROM partners')}
        aliases=_public_source_aliases(conn,rows)
    recs[:]=accepted
    for rec in recs:
        rec.recommendationReason=redact_sources(_display_source_aliases(rec.recommendationReason,aliases),labels)
        # Private identity for the same adopted card when the writer rechecks after redaction.
        accepted_items[rec.partnerId]['_public_recommendation_reason']=rec.recommendationReason
        rec.riskNotes=redact_sources(_display_source_aliases(rec.riskNotes,aliases),labels)
    gap=redact_sources(_display_source_aliases(output.get('gapAnalysis') or '',aliases),labels) if analysis_valid else ''
    for name in sorted(known_names-allowed_names,key=len,reverse=True):
        gap=gap.replace(name,'[未通过校验的伙伴]')
    answer=gap if recs else '本次暂无推荐伙伴。'
    if not recs and plans:
        answer+=' 未来规划线索：'+'、'.join(plans)+'。'
    if not recs and gap:
        answer+='\n\n'+gap
    incomplete=bool(rejected or unsupported or not analysis_valid or any(not row[1].get('inputCoverage',{}).get('complete',True) for row in rows))
    return {'answer':answer,'supplyStatus':output.get('supplyStatus','unknown') if analysis_valid else 'unknown',
            'gapAnalysis':gap,'analysisComplete':not incomplete,'recommendations':[rec.model_dump() for rec in recs],
            'adopted_cards':adopted,'analysisRefs':refs if analysis_valid else [],'analysis_adopted':analysis_valid}


def _context_excerpt(value: str | None, limit: int) -> str:
    """Use existing text without another model call or reading raw attachments."""
    text = (value or '').strip()
    return text if len(text) <= limit else text[:limit] + '…（摘要截取）'


class _MatchExecutionLost(HTTPException):
    def __init__(self):
        super().__init__(409, '任务状态已变化，请刷新查看当前结果')


def _require_match_run(conn, record_id, run_id, allowed_statuses=('matching', 'enriching')):
    """Check ownership under the same writer lock as recovery, retry and saving."""
    conn.lock_writer()
    row = conn.execute('SELECT task_status FROM match_records WHERE id=?', (record_id,)).fetchone()
    snapshot = understanding.load(conn, record_id) or {}
    if (not run_id or not row or row['task_status'] not in allowed_statuses
            or snapshot.get('progress', {}).get('run_id') != run_id):
        raise _MatchExecutionLost()
    return snapshot


def _match_stage(record_id, snapshot, key, state):
    if not snapshot.get('progress'):
        return
    with get_db() as conn:
        conn.lock_writer()
        row = conn.execute('SELECT task_status FROM match_records WHERE id=?', (record_id,)).fetchone()
        current = understanding.load(conn, record_id) or {}
        if not row or row['task_status'] not in ('matching', 'enriching') or current.get('progress',{}).get('run_id') != snapshot['progress']['run_id']:
            raise _MatchExecutionLost()
        task_progress.stage(snapshot['progress'], key, state)
        understanding.save(conn, record_id, snapshot)
        conn.execute('UPDATE match_records SET updated_at=? WHERE id=?', (task_progress.now(), record_id))


def _detail_content(requirement, snapshot, rows):
    # Keep one complete demand; use only demand facts, not follow-ups or tag proposals.
    fact_fields = ('customerName','projectName','industry','region','projectStage',
                   'businessNeeds','technicalNeeds','deliveryNeeds','qualificationRequirements',
                   'caseRequirements','onsiteRequirement','timelineRequirement',
                   'cloudPlatformPreference','deliveryTypeTags')
    extracted = snapshot['understanding']['facts']
    facts = {key:extracted[key] for key in fact_fields
             if key in extracted and extracted[key] != requirement}
    return json.dumps({'requirement':requirement,'facts':facts,
                       'candidates':[match_context.provider_context(row[1]) for row in rows]},
                      ensure_ascii=False,separators=(',',':'))


def _perform_partner_match(requirement: str, snapshot: dict) -> list[PartnerRecommendation]:
    """Understanding is saved before local PG recall and candidate model review."""
    _match_stage(snapshot['_task_id'], snapshot, 'initial_selection', 'running')
    with get_db() as conn:
        conn.begin_read()
        candidate_stamp = _candidate_stamp(conn)
        recall_info = {}
        selected = match_context.recall_candidates(conn,requirement,snapshot['understanding']['facts'],diagnostics=recall_info)
    snapshot['candidate_stamp'] = candidate_stamp
    snapshot['initial_selection'] = {'input_stamp':candidate_stamp,'candidates':selected,'method':'postgres_keywords','recall':recall_info}
    match_context.log_match_metadata('RECALL',task_id=snapshot['_task_id'],input_version=candidate_stamp,**recall_info)
    _match_stage(snapshot['_task_id'], snapshot, 'initial_selection', 'completed')
    if not selected:
        snapshot['outcome'] = {'answer':'本次未召回候选伙伴。','supplyStatus':'unknown','gapAnalysis':'','analysisComplete':True,'recommendations':[]}
        return []

    _match_stage(snapshot['_task_id'], snapshot, 'detailed_review', 'running')

    detail_start = perf_counter()
    try:
        with get_db() as conn:
            conn.begin_read()
            rows = [match_context.detailed_candidate(conn, item['partnerId'], item['verificationFocus'],
                    requirement, recall_terms=item.get('recallTerms',[]),
                    facts=snapshot['understanding']['facts'], hits=item['hits']) for item in selected]
        schema = understanding.MatchAnswer.model_json_schema()
        try:
            config, chars, tokens = match_context.assemble_details(
                rows, pinned_configuration(snapshot['model']),
                lambda current_rows:_detail_content(requirement,snapshot,current_rows), schema)
        finally:
            snapshot['detail_input_coverage']={r[0]['id']:r[1]['inputCoverage'] for r in rows}
            snapshot['detail_source_map']={r[0]['id']:r[1]['_sourceMap'] for r in rows}
        detail_messages = matching.detail_messages(_detail_content(requirement,snapshot,rows))
        _match_stage(snapshot['_task_id'],snapshot,'detailed_review','running')
        prepared = round((perf_counter() - detail_start) * 1000)
        call_start = perf_counter()
        reset_retry_count()
        try:
            raw = development_model.completion({**config, '_match_request': True}, detail_messages, schema)
        finally:
            match_context.log_stage('detailed_review', len(selected), chars, tokens, prepared,
                                    round((perf_counter() - call_start) * 1000), last_retry_count())
        try:output, parse_rejections = matching.parse_answer(raw)
        except Exception as error:
            error.model_call_failure=True
            raise
        snapshot['model_output'] = output
        snapshot['detail_rows'] = [[{key:row[0].get(key) for key in ('id','name','capabilities','industries','service_areas')},row[1],row[2],row[3]] for row in rows]
        partners = [row[0] for row in rows]
        cases = {row[0]['id']: row[2] for row in rows}
        deliverables = {row[0]['id']: row[3] for row in rows}
        rejections: list[str] = list(parse_rejections)
        by_id = {r[0]['id']:r for r in rows}
        legal_items = []
        for item in output['recommendations']:
            if _source_assessment(item,by_id.get(item['partnerId'])) is None:
                rejections.append('推荐含不属于实际已发送来源范围的引用')
            else:
                legal_items.append(item)
        recs = _validated_recommendations(legal_items,partners,cases,deliverables,rejections)
        snapshot['rejection_codes']=rejections
        evidence_filtered = bool(rejections)
        if output['_raw_recommendation_count'] and not recs and not (output['_analysis_shape_valid'] and output['gapAnalysis']):
            raise ValueError('所有主结果均未通过校验：' + '；'.join(rejections[:10]))
        snapshot['outcome'] = _validated_outcome(recs, output, bool(rejections) or evidence_filtered, rows,requirement=requirement,facts=snapshot['understanding']['facts'])
        if legal_items and not recs and not snapshot['outcome']['analysis_adopted'] and not any(i['evidenceType'] in ('planning_only','unrelated') for i in legal_items):
            raise ValueError('所有采用结果的实际依赖均已失效')
        match_context.log_match_metadata('REVIEW',task_id=snapshot['_task_id'],input_version=candidate_stamp,
                                        rules_version=matching.MATCHING_RULES_VERSION,
                                        raw_recommendation_count=len(output['recommendations']),
                                        valid_recommendation_count=len(recs),rejection_count=len(rejections),
                                        evidence_references_filtered=evidence_filtered)
        return recs
    except ModelConfigurationError as exc:
        raise PublicTaskError(exc, 503) from None
    except Exception as exc:
        raise PublicTaskError(exc) from None


def _candidate_stamp(connection=None):
    from ..profile_sources import sources, stamp
    with (nullcontext(connection) if connection is not None else get_db()) as conn:
        return fingerprint({
            'matching_rules': matching.MATCHING_RULES_VERSION,
            'source_versions': [(p['id'],s['kind'],s['id'],stamp(s)) for p in conn.execute('SELECT id FROM partners ORDER BY id') for s in sources(conn,p['id'])],
            'partners': [dict(r) for r in conn.execute('SELECT id,status,name,capabilities,industries,service_areas,materials_revision,profile_materials_revision,profile_updated_at,updated_at FROM partners ORDER BY id')],
            'cases': [dict(r) for r in conn.execute('SELECT id,partner_id,title,visible,updated_at FROM cases ORDER BY id')],
            'deliverables': [dict(r) for r in conn.execute('SELECT id,case_id,filename,processed_at FROM deliverables ORDER BY id')],
            'contributions': [dict(r) for r in conn.execute('SELECT partner_id,source_kind,source_id,source_fingerprint,state,sections_json FROM partner_profile_sources ORDER BY partner_id,source_kind,source_id')],
        })


class DeletedMatchPartnerError(ValueError):
    """A candidate was deleted while a model request was running."""


def _set_task_state(
    record_id: str,
    task_status: str,
    error_stage: str | None = None,
    recommendations: list[PartnerRecommendation] | None = None,
    failures: list[dict] | None = None,
    snapshot: dict | None = None,
    expected_run_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    details=json.dumps(failures,ensure_ascii=False) if failures else None
    with get_db() as conn:
        conn.lock_writer()
        stored = understanding.load(conn, record_id) or {}
        current = conn.execute('SELECT task_status FROM match_records WHERE id=?', (record_id,)).fetchone()
        if expected_run_id and (not current or current['task_status'] not in ('matching','enriching') or stored.get('progress',{}).get('run_id') != expected_run_id):
            return
        if snapshot and snapshot.get('progress') and (not current or current['task_status'] not in ('matching','enriching') or stored.get('progress',{}).get('run_id') != snapshot['progress']['run_id']):
            raise _MatchExecutionLost()
        if recommendations is None:
            cursor = conn.execute(
                "UPDATE match_records SET task_status = ?, last_error_stage = ?, last_error_details = ?, updated_at = ? WHERE id = ?",
                (task_status, error_stage, details, now, record_id),
            )
        else:
            # Serialize against partner deletion: late model results must not create
            # dangling JSON references after the candidate snapshot was read.
            if snapshot is not None and snapshot.get('format_version')==2 and snapshot.get('model_output'):
                output=snapshot['model_output']
                old_count=len(recommendations)
                snapshot['outcome']=_validated_outcome(recommendations,output,bool(snapshot.get('rejection_codes')),snapshot['detail_rows'],connection=conn)
                if old_count and not recommendations and not snapshot['outcome']['gapAnalysis']:
                    if any(conn.execute('SELECT 1 FROM partners WHERE id=?',(row[0]['id'],)).fetchone() is None for row in snapshot['detail_rows']):
                        raise DeletedMatchPartnerError('推荐伙伴已删除，请重新生成推荐')
                    raise ValueError('所有采用结果的实际依赖均已失效')
            if any(conn.execute("SELECT 1 FROM partners WHERE id = ?", (item.partnerId,)).fetchone() is None for item in recommendations):
                raise DeletedMatchPartnerError("推荐伙伴已删除，请重新生成推荐")
            cursor = conn.execute(
                """UPDATE match_records
                   SET recommendations_json = ?, task_status = ?, last_error_stage = ?, last_error_details = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    json.dumps([item.model_dump() for item in recommendations], ensure_ascii=False),
                    task_status, error_stage, details, now, record_id,
                ),
            )
        if cursor.rowcount != 1:
            raise RuntimeError("task state update target was not found")
        if snapshot is not None:
            if snapshot.get('progress') and task_status == 'enriching':
                current_stage = next(s for s in snapshot['progress']['stages'] if s['key']=='detailed_review')
                if current_stage['status']=='running': task_progress.stage(snapshot['progress'],'detailed_review','completed')
            snapshot["visible_answer"]=snapshot["outcome"]["answer"]
            understanding.save(conn,record_id,snapshot)
        if task_status in ('ready','partial','failed'):
            stored = snapshot or stored
            task_progress.finish(stored.get('progress'), failed=task_status != 'ready')
            if stored: understanding.save(conn,record_id,stored)


def _claim_task_retry(record_id: str, current_status: str, next_status: str, user_id: str, run_id: str) -> None:
    """Atomically prevent two retry requests from running the same task."""
    with get_db() as conn:
        conn.lock_writer()
        ensure_account_active(conn, user_id)
        cursor = conn.execute(
            """UPDATE match_records
               SET task_status = ?, last_error_stage = NULL, last_error_details = NULL, updated_at = ?
               WHERE id = ? AND task_status = ?""",
            (next_status, datetime.now(timezone.utc).isoformat(), record_id, current_status),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="任务状态已变化，请刷新后再试")
        cached = understanding.load(conn, record_id) or {}
        cached['agent_execution'] = agent_settings.execution(conn,'partner_match',accept=True,model_config_id=(cached.get('agent_execution') or {}).get('modelConfigId'))
        cached['progress'] = task_progress.new('partner_match', run_id)
        understanding.save(conn, record_id, cached)


def _run_task_enrichment(
    record_id: str,
    requirement: str,
    recommendations: list[PartnerRecommendation],
    created_at: str,
    *,
    include_tag_suggestions: bool,
    snapshot: dict,
    refresh: bool = False,
) -> str:
    """Generate missing task derivatives and persist a truthful final task state."""
    run_id = snapshot['progress']['run_id']
    with get_db() as conn:
        demand_exists = conn.execute(
            "SELECT 1 FROM demand_profiles WHERE match_record_id = ? LIMIT 1", (record_id,),
        ).fetchone() is not None
        opportunity_exists = conn.execute(
            "SELECT 1 FROM project_opportunities WHERE match_record_id = ? LIMIT 1", (record_id,),
        ).fetchone() is not None

    failed_stages: list[str] = []
    failures: list[dict] = []
    if not demand_exists or refresh:
        bind_context(stage="demand_profile")
        try:
            _generate_demand_profile(record_id, requirement, recommendations, created_at,
                data={**snapshot['understanding']['facts'],**snapshot['outcome']}, expected_run_id=run_id)
            demand_exists = True
        except _MatchExecutionLost:
            raise
        except Exception as exc:
            failures.append(failure("demand_profile",exc))
            failed_stages.append("demand_profile")
            print(f"[WARN] demand profile generation failed for task {record_id}", flush=True)

    if include_tag_suggestions:
        bind_context(stage="tag_suggestion")
        if not _generate_tag_suggestions(requirement, record_id,
                items=snapshot['understanding']['tag_suggestions'], expected_run_id=run_id):
            failures.append(failure("tag_suggestion"));failed_stages.append("tag_suggestion")
            print(f"[WARN] tag suggestion generation failed for task {record_id}", flush=True)

    if not opportunity_exists or refresh:
        bind_context(stage="project_opportunity")
        opportunity_exists = _extract_project_opportunity(requirement, record_id, recommendations,
            failures=failures, data=snapshot['understanding']['facts'], expected_run_id=run_id)
        if not opportunity_exists:
            failed_stages.append("project_opportunity")

    bind_context(stage="persistence")
    final_status = "ready" if demand_exists and opportunity_exists and not failed_stages else "partial"
    _set_task_state(record_id, final_status, ",".join(failed_stages) or None, failures=failures, expected_run_id=run_id)
    return final_status


@router.post("/match", response_model=MatchResponse)
def match_partners(req: MatchRequest, user: dict = Depends(require_active_user)) -> MatchResponse:
    if not req.requirement.strip():
        raise HTTPException(422, detail="请输入项目需求")
    record_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_db() as conn:
            conn.lock_writer()
            ensure_account_active(conn, user['id'])
            conn.execute(
                """INSERT INTO match_records
                   (id, requirement, recommendations_json, created_at, created_by, owner_user_id,
                    task_status, last_error_stage, updated_at)
                   VALUES (?, ?, '[]', ?, ?, ?, 'matching', NULL, ?)""",
                (record_id, req.requirement, now, user["username"], user["id"], now),
            )
            understanding.save(conn,record_id,{'agent_execution':agent_settings.execution(conn,'partner_match',accept=True,model_config_id=req.modelConfigId),'requested_model_config_id':req.modelConfigId,'progress':task_progress.new('partner_match',run_id,now)})
    except HTTPException:
        raise
    except Exception as error:
        record_error(error, "submission", task_id=record_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="服务异常，请联系管理员。")

    return _execute_match(record_id, req.requirement, now, run_id)


def _execute_match(record_id: str, requirement: str, created_at: str, run_id: str) -> MatchResponse:
    with get_db() as conn:snapshot=understanding.load(conn,record_id) or {}
    with diagnostic_scope(task_id=record_id, stage='partner_match'), agent_settings.execution_scope(snapshot.get('agent_execution')):
        return _execute_match_inner(record_id, requirement, created_at, run_id)


def _execute_match_inner(record_id: str, requirement: str, created_at: str, run_id: str) -> MatchResponse:
    stage = 'understanding'
    with get_db() as conn:
        cached = _require_match_run(conn, record_id, run_id, ('matching',))
        row = conn.execute('SELECT recommendations_json FROM match_records WHERE id=?',(record_id,)).fetchone()
    snapshot = cached
    bind_context(stage='understanding',run_id=(snapshot.get('progress') or {}).get('run_id'),request_id=record_id)
    saved_recommendations = json.loads(row['recommendations_json'])
    try:
        _match_stage(record_id, snapshot, 'understanding', 'running')
        prepared = understanding.prepare(requirement, cached)
        reusable = prepared is cached and bool(cached.get('outcome')) and cached.get('candidate_stamp') == _candidate_stamp()
        if prepared is not cached:
            prepared['requested_model_config_id'] = cached.get('requested_model_config_id')
            prepared['agent_execution'] = cached.get('agent_execution')
            prepared['progress'] = cached.get('progress')
            prepared['visible_answer'] = cached.get('visible_answer','')
        snapshot = prepared
        snapshot['_task_id'] = record_id
        _match_stage(record_id, snapshot, 'understanding', 'completed')
        if not snapshot['understanding']['in_scope']:
            _set_task_state(record_id,'ready',expected_run_id=run_id)
            return MatchResponse(requirement=requirement,recommendations=[],recordId=record_id,taskStatus='ready')
        stage = 'partner_match';bind_context(stage=stage,run_id=(snapshot.get('progress') or {}).get('run_id'))
        recs = [PartnerRecommendation.model_validate(item) for item in saved_recommendations] if reusable else _perform_partner_match(requirement,snapshot)
        _set_task_state(record_id, 'enriching', recommendations=recs, snapshot=snapshot)
        saved_recommendations = recs
        stage = 'persistence';bind_context(stage=stage)
        _match_stage(record_id, snapshot, 'enrichment', 'running')
        task_status = _run_task_enrichment(record_id, requirement, recs, created_at,
            include_tag_suggestions=True, snapshot=snapshot, refresh=not reusable)
        return MatchResponse(requirement=requirement,recommendations=recs,recordId=record_id,taskStatus=task_status)
    except _MatchExecutionLost:
        raise
    except Exception as error:
        # A successful earlier result stays readable, including on a later retry.
        try:
            _set_task_state(record_id, 'partial' if saved_recommendations or snapshot.get('visible_answer') else 'failed', stage,
                            failures=[failure(stage,error)], expected_run_id=run_id)
        except Exception as persistence_error:
            record_error(persistence_error,'persistence',task_id=record_id)
        if isinstance(error, HTTPException): raise
        error_status = 409 if isinstance(error, DeletedMatchPartnerError) else 503 if isinstance(error, ModelConfigurationError) else 502
        raise PublicTaskError(error, error_status) from error


def _process_created_task(record_id: str, requirement: str, created_at: str, run_id: str) -> None:
    try:
        _execute_match(record_id, requirement, created_at, run_id)
    except _MatchExecutionLost:
        return
    except Exception as error:
        # Stage-specific errors already recorded inside the worker are deduplicated.
        # Also cover snapshot/query/parse failures before its inner try block.
        record_error(error, 'partner_match', task_id=record_id, run_id=run_id, request_id=record_id)
        print(f"[WARN] background processing failed for task {record_id}", flush=True)


@router.post("/tasks", response_model=TaskAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_task(req: TaskCreateRequest, user: dict = Depends(require_active_user)) -> TaskAccepted:
    bind_context(task_id=str(req.requestId), request_id=str(req.requestId), stage="submission")
    requirement = req.requirement
    if not requirement.strip():
        raise HTTPException(422, detail="请输入项目需求")
    record_id = str(req.requestId)
    stamp = task_progress.now()
    run_id = str(uuid.uuid4())
    try:
        with get_db() as conn:
            conn.lock_writer()
            ensure_account_active(conn,user['id'])
            existing = conn.execute('SELECT owner_user_id,requirement,task_status FROM match_records WHERE id=?',(record_id,)).fetchone()
            if existing:
                if existing['owner_user_id'] != user['id']: raise HTTPException(404,'任务不存在')
                if existing['requirement'] != requirement: raise HTTPException(409,'该提交标识已用于其他需求，请重新发起任务')
                saved = understanding.load(conn,record_id) or {}
                if saved.get('requested_model_config_id') != req.modelConfigId:raise HTTPException(409,'同一提交标识不能用于不同模型，请重新发起任务')
                return TaskAccepted(recordId=record_id,runId=saved.get('progress',{}).get('run_id'),taskStatus=existing['task_status'])
            conn.execute("""INSERT INTO match_records(id,requirement,recommendations_json,created_at,created_by,owner_user_id,task_status,updated_at)
                VALUES (?,?,'[]',?,?,?,'matching',?)""",(record_id,requirement,stamp,user['username'],user['id'],stamp))
            understanding.save(conn,record_id,{'agent_execution':agent_settings.execution(conn,'partner_match',accept=True,model_config_id=req.modelConfigId),'requested_model_config_id':req.modelConfigId,'progress':task_progress.new('partner_match',run_id,stamp)})
    except HTTPException:raise
    except Exception as error:
        record_error(error,'submission',task_id=record_id,request_id=record_id)
        raise HTTPException(500,'服务异常，请联系管理员。') from error

    # get_db has independently committed. No model work can run before this line.
    try:
        executor.submit(_process_created_task,record_id,requirement,stamp,run_id)
    except RuntimeError as error:
        _set_task_state(record_id,'failed','interrupted',failures=[failure('interrupted',error)],expected_run_id=run_id)
        return TaskAccepted(recordId=record_id,runId=run_id,taskStatus='failed')
    return TaskAccepted(recordId=record_id,runId=run_id,taskStatus='matching')


def _save_derivative(conn, table, columns, values, *, expected_run_id=None):
    if expected_run_id is not None:
        _require_match_run(conn, values[1], expected_run_id, ('enriching',))
    else:
        # Explicit maintenance extraction is outside the task executor.
        conn.lock_writer()
    row=conn.execute('SELECT id FROM '+table+' WHERE match_record_id=? ORDER BY created_at DESC LIMIT 1',(values[1],)).fetchone()
    if row:
        updates=[(k,v) for k,v in zip(columns,values) if k not in ('id','created_at')]
        conn.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k,_ in updates)+' WHERE id=?',[v for _,v in updates]+[row['id']])
    else:
        conn.execute('INSERT INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',values)


def _extract_project_opportunity(
    requirement: str, match_record_id: str, recommendations: list[PartnerRecommendation],
    *, data: dict, failures: list[dict] | None = None,
    expected_run_id: str | None = None,
) -> bool:
    try:
        rec_names = ", ".join(r.partnerName for r in recommendations[:5])
        data=normalize_opportunity(data)
        # Calculate completeness
        completeness, missing = calculate_opportunity_completeness(data)

        # Get matched capabilities from demand profile
        with get_db() as conn:
            dp = conn.execute("SELECT capability_tags, supply_status FROM demand_profiles WHERE match_record_id = ?", (match_record_id,)).fetchone()
            cap_tags = dp["capability_tags"] if dp else ""
            supply = dp["supply_status"] if dp else ""

        now = datetime.now(timezone.utc).isoformat()
        opp_id = str(uuid.uuid4())
        with get_db() as conn:
            _save_derivative(conn,
                'project_opportunities', ['id', 'match_record_id', 'requirement_text', 'customer_name', 'project_name', 'industry', 'region', 'project_stage', 'business_needs', 'technical_needs', 'delivery_needs', 'qualification_requirements', 'case_requirements', 'onsite_requirement', 'timeline_requirement', 'cloud_platform_preference', 'matched_capability_tags', 'unmatched_capability_signals', 'recommended_partner_ids', 'recommended_partner_names', 'supply_status', 'completeness_score', 'missing_fields', 'follow_up_questions', 'created_at', 'updated_at'],
                (opp_id, match_record_id, requirement, data.get("customerName","未识别"), data.get("projectName","未识别"), data.get("industry","未识别"), data.get("region","未识别"), data.get("projectStage","未识别"), data.get("businessNeeds","未识别"), data.get("technicalNeeds","未识别"), data.get("deliveryNeeds","未识别"), data.get("qualificationRequirements","未识别"), data.get("caseRequirements","未识别"), data.get("onsiteRequirement","未识别"), data.get("timelineRequirement","未识别"), data.get("cloudPlatformPreference","未识别"), cap_tags, "", "", rec_names, supply, completeness, ",".join(missing), json.dumps(data.get("followUpQuestions",[]), ensure_ascii=False), now, now),
                expected_run_id=expected_run_id,
            )
        return True
    except _MatchExecutionLost:
        raise
    except Exception as exc:
        record_error(exc, "project_opportunity", task_id=match_record_id)
        if failures is not None:failures.append(failure("project_opportunity",exc))
        print(f"[WARN] project opportunity extraction failed for task {match_record_id}", flush=True)
        return False


def _generate_tag_suggestions(requirement: str, match_record_id: str, *, items: list,
                              expected_run_id: str | None = None) -> bool:
    try:
        with get_db() as conn:
            std_tags = [r["name"] for r in conn.execute("SELECT name FROM capability_tags WHERE enabled = 1").fetchall()]
            existing_sugs = {r["suggested_name"] for r in conn.execute("SELECT suggested_name FROM capability_tag_suggestions WHERE status = 'pending'").fetchall()}
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            if expected_run_id is not None:
                _require_match_run(conn, match_record_id, expected_run_id, ('enriching',))
            else:
                conn.lock_writer()
            for item in items:
                name = item.get("suggestedName", "").strip()
                if not name or name in std_tags or name in existing_sugs:
                    continue
                existing = conn.execute("SELECT id, occurrence_count FROM capability_tag_suggestions WHERE suggested_name = ? AND status = 'pending'", (name,)).fetchone()
                if existing:
                    conn.execute("UPDATE capability_tag_suggestions SET occurrence_count = occurrence_count + 1, updated_at = ? WHERE id = ?", (now, existing["id"]))
                else:
                    conn.execute(
                        "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_id, suggested_category_name, description, evidence_text, source_requirement, source_match_record_id, confidence, occurrence_count, status, created_at, updated_at, adopted_at) VALUES (?,?,?,?,?,?,?,?,?,1,'pending',?,?,NULL)",
                        (str(uuid.uuid4()), name, None, item.get("suggestedCategoryName", "其他"), item.get("description", ""), item.get("evidenceText", ""), requirement, match_record_id, float(item.get("confidence", 0.5)), now, now)
                    )
                existing_sugs.add(name)
        return True
    except _MatchExecutionLost:
        raise
    except Exception as error:
        record_error(error, "tag_suggestion", task_id=match_record_id)
        return False




def _generate_demand_profile(
    match_record_id: str,
    requirement: str,
    recs: list[PartnerRecommendation],
    created_at: str,
    *, data: dict, expected_run_id: str | None = None,
) -> None:
    """Persist facts from the same understanding; no second extraction request."""
    partner_count=len(recs)
    top_names=", ".join(r.partnerName for r in recs[:3])
    supply_status='unknown'
    # Get enabled standard capability tags for LLM constraint
    with get_db() as conn:
        std_tags = [r["name"] for r in conn.execute("SELECT name FROM capability_tags WHERE enabled = 1").fetchall()]

    try:
        industry_tags = canonical(data.get("industry", data.get("industryTags", "")), "industry")
        capability_tags = _to_str(data.get("capabilityTags", ""))
        # Post-filter: only keep tags that exist in standard dictionary
        if capability_tags:
            cap_list = [t.strip() for t in capability_tags.split(",") if t.strip()]
            capability_tags = ", ".join(t for t in cap_list if t in std_tags)
        delivery_type_tags = data.get("deliveryTypeTags", "")
        region_tags = canonical(data.get("region", data.get("regionTags", "")), "region")
        complexity_level = data.get("complexityLevel", "中")
        urgency_level = data.get("urgencyLevel", "中")
        project_keywords = data.get("projectKeywords", "")
        llm_supply_status = data.get("supplyStatus", supply_status)
        gap_analysis = data.get("gapAnalysis", "")
    except Exception as error:
        record_error(error, "demand_profile", task_id=match_record_id)
        raise

    profile_id = str(uuid.uuid4())
    with get_db() as conn:
        _save_derivative(conn,
            'demand_profiles', ['id', 'match_record_id', 'requirement_text', 'industry_tags', 'capability_tags', 'delivery_type_tags', 'region_tags', 'complexity_level', 'urgency_level', 'project_keywords', 'matched_partner_count', 'top_partner_names', 'supply_status', 'gap_analysis', 'created_at'],
            (profile_id, match_record_id, requirement, industry_tags, capability_tags, delivery_type_tags, region_tags, complexity_level, urgency_level, project_keywords, partner_count, top_names, llm_supply_status, gap_analysis, created_at),
            expected_run_id=expected_run_id,
        )


@router.post("/tasks/{record_id}/retry", response_model=MatchResponse)
def retry_match_record(record_id: str, user: dict = Depends(require_active_user)) -> MatchResponse:
    bind_context(task_id=record_id, stage="partner_match")
    _recover_accessible_task(record_id, user)
    with get_db() as conn:
        row = conn.execute(
            """SELECT id, requirement, recommendations_json, created_at, owner_user_id, task_status
               FROM match_records WHERE id = ?""",
            (record_id,),
        ).fetchone()
    if row is None or (row["owner_user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="推荐任务不存在")
    if row["task_status"] == "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="任务已完成，无需重试")
    if row["task_status"] in {"matching", "enriching"}:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="任务正在处理中，请稍后再试")

    requirement=row['requirement'];created_at=row['created_at']
    run_id = str(uuid.uuid4())
    _claim_task_retry(record_id,row['task_status'],'matching',user['id'],run_id)
    return _execute_match(record_id,requirement,created_at,run_id)


@router.patch("/tasks/{record_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_match_record(record_id: str, user: dict = Depends(require_active_user)):
    from .. import development_lifecycle as life
    with get_db() as conn:
        exists=conn.execute('SELECT id FROM development_plans WHERE id=?',(record_id,)).fetchone()
    if exists:
        life.archive(record_id,user,restore=False)
        return
    with get_db() as conn:
        row = conn.execute("SELECT id, owner_user_id FROM match_records WHERE id = ?", (record_id,)).fetchone()
        if row is None or (row["owner_user_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="推荐任务不存在")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE match_records SET archived_at = ?, updated_at = ? WHERE id = ?", (now, now, record_id))


@router.patch("/tasks/{record_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_match_record(record_id: str, user: dict = Depends(require_active_user)):
    from .. import development_lifecycle as life
    with get_db() as conn:
        exists=conn.execute('SELECT id FROM development_plans WHERE id=?',(record_id,)).fetchone()
    if exists:
        life.archive(record_id,user,restore=True)
        return
    with get_db() as conn:
        row = conn.execute("SELECT id, owner_user_id FROM match_records WHERE id = ?", (record_id,)).fetchone()
        if row is None or (row["owner_user_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="推荐任务不存在")
        conn.execute(
            "UPDATE match_records SET archived_at = NULL, updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), record_id),
        )
