export const SKILL_CATEGORIES = [
  "智能匹配",
  "伙伴洞察",
  "能力发展",
  "项目机会",
] as const;

export type SkillCategory = (typeof SKILL_CATEGORIES)[number];

export type SkillId =
  | "enablement_workspace"
  | "partner_match"
  | "partner_profile"
  | "partner_capability_analysis"
  | "partner_case_search"
  | "partner_gap_analysis"
  | "demand_profile"
  | "project_opportunity_extract"
  | "capability_tag_suggest";

export type SkillDefinition = {
  id: SkillId;
  name: string;
  description: string;
  category: SkillCategory;
  tags: string[];
  enabled: boolean;
  capabilityReference: string;
  inputDefinition: string;
};

/**
 * 轻量能力注册表：只描述现有业务能力及其入口，不承载执行编排。
 * enabled=false 表示当前没有可独立执行的底层能力。
 */
export const SKILL_REGISTRY: readonly SkillDefinition[] = [
  {
    id: "enablement_workspace", name: "伙伴能力发展助手", category: "能力发展",
    description: "结构化收集诉求，诊断目标并检索获准资源，生成、调整、编辑和确认版本。",
    tags: ["诉求整理", "资源检索"], enabled: true,
    capabilityReference: "POST /development/plans、GET /enablement/resources",
    inputDefinition: "伙伴、来源任务或共享案例标识，以及资源筛选条件",
  },
  {
    id: "partner_match",
    name: "伙伴智能匹配",
    description: "基于项目需求和已有伙伴证据生成推荐短名单。",
    category: "智能匹配",
    tags: ["伙伴推荐", "需求匹配", "证据支撑"],
    enabled: true,
    capabilityReference: "POST /agent/match",
    inputDefinition: "项目需求自然语言描述",
  },
  {
    id: "partner_profile",
    name: "伙伴资料查询",
    description: "读取伙伴基础资料、能力标签、行业与区域信息。",
    category: "伙伴洞察",
    tags: ["伙伴资料", "能力标签", "行业经验"],
    enabled: true,
    capabilityReference: "GET /partners、GET /partners/{partner_id}",
    inputDefinition: "伙伴名称或伙伴 ID",
  },
  {
    id: "partner_capability_analysis",
    name: "伙伴能力分析",
    description: "复用现有伙伴 AI 画像生成和画像查询能力。",
    category: "伙伴洞察",
    tags: ["AI画像", "能力分析", "伙伴洞察"],
    enabled: true,
    capabilityReference: "GET /partners/profiles、POST /partners/{partner_id}/profile",
    inputDefinition: "伙伴 ID",
  },
  {
    id: "partner_case_search",
    name: "伙伴案例查询",
    description: "按伙伴读取已有项目案例和交付物证据。",
    category: "伙伴洞察",
    tags: ["项目案例", "行业实践", "交付物"],
    enabled: true,
    capabilityReference: "GET /cases/by-partner/{partner_id}",
    inputDefinition: "伙伴 ID",
  },
  {
    id: "partner_gap_analysis",
    name: "伙伴能力短板分析",
    description: "面向目标项目独立分析伙伴能力缺口。",
    category: "能力发展",
    tags: ["能力短板", "差距分析", "发展建议"],
    enabled: false,
    capabilityReference: "暂无独立接口；当前仅在 /agent/match 推荐结果中提供风险或缺口提示",
    inputDefinition: "伙伴、目标项目与能力要求",
  },
  {
    id: "demand_profile",
    name: "需求画像生成",
    description: "将匹配需求沉淀为结构化需求画像。",
    category: "智能匹配",
    tags: ["需求画像", "结构化分析", "供需状态"],
    enabled: true,
    capabilityReference: "由 POST /agent/match 内部调用，结果通过 GET /agent/tasks/{id} 查询",
    inputDefinition: "项目需求及匹配结果",
  },
  {
    id: "project_opportunity_extract",
    name: "项目机会识别",
    description: "从匹配需求中抽取并沉淀项目机会。",
    category: "项目机会",
    tags: ["机会识别", "运营跟进", "需求沉淀"],
    enabled: true,
    capabilityReference: "由 POST /agent/match 内部调用，结果通过 GET /agent/tasks/{id} 查询",
    inputDefinition: "项目需求及推荐伙伴",
  },
  {
    id: "capability_tag_suggest",
    name: "能力标签建议",
    description: "根据需求证据生成待管理员采纳的能力标签建议。",
    category: "能力发展",
    tags: ["标签建议", "人工采纳", "能力发展"],
    enabled: true,
    capabilityReference: "POST /admin/capability-tags/suggestions/scan",
    inputDefinition: "现有需求画像与标准能力标签",
  },
] as const;

export const SKILLS_BY_ID = Object.fromEntries(
  SKILL_REGISTRY.map((skill) => [skill.id, skill]),
) as Record<SkillId, SkillDefinition>;
