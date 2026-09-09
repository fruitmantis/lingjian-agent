import type { SkillId } from "./skills";

export const SCENE_CATEGORIES = [
  "全部",
  "智能匹配",
  "伙伴洞察",
  "能力发展",
  "项目机会",
  "运营分析",
] as const;

export type SceneCategory = Exclude<(typeof SCENE_CATEGORIES)[number], "全部">;
export type SceneAvailability = "ready" | "embedded" | "building" | "preparation";

export type SceneDefinition = {
  id: string;
  name: string;
  description: string;
  category: SceneCategory;
  skillId: SkillId;
  exampleQueries: string[];
  tags: string[];
  enabled: boolean;
  sortOrder: number;
  availability: SceneAvailability;
  actionHref?: string;
  actionLabel: string;
};

/**
 * 用户视角的场景注册表。Scene 只映射 Skill，不包含路由、意图识别或执行编排。
 */
export const SCENE_REGISTRY: readonly SceneDefinition[] = [
  {
    id: "partner-enablement-prepare", name: "制定伙伴能力发展建议",
    description: "选择伙伴并描述发展方向，结合当前画像生成建议，继续解释、比较和调整。",
    category: "能力发展", skillId: "enablement_workspace", exampleQueries: ["整理伙伴服务能力发展诉求"],
    tags: ["伙伴发展", "诉求整理"], enabled: true, sortOrder: 61,
    availability: "ready", actionHref: "/?mode=development", actionLabel: "制定发展建议",
  },
  {
    id: "enablement-resource-search", name: "查找课程与实验",
    description: "按名称、用途、技术方向与能力检索当前已发布的课程与实验，无需先选择伙伴。",
    category: "能力发展", skillId: "enablement_workspace", exampleQueries: ["查找数据库迁移课程与实验"],
    tags: ["课程", "实验", "资源检索"], enabled: true, sortOrder: 62,
    availability: "ready", actionHref: "/resources?resource_type=course", actionLabel: "查找资源",
  },
  {
    id: "enablement-shared-cases", name: "学习优秀伙伴案例",
    description: "查看已核验的共享学习版本，了解贡献伙伴的实践方法与实际角色。",
    category: "能力发展", skillId: "enablement_workspace", exampleQueries: ["查找可学习的伙伴实践案例"],
    tags: ["共享案例", "实践方法"], enabled: true, sortOrder: 63,
    availability: "ready", actionHref: "/resources?resource_type=case", actionLabel: "查看共享案例",
  },
  {
    id: "enablement-advice-revise", name: "调整已有发展建议",
    description: "进入已有发展任务，用自然语言解释、比较或修改建议。",
    category: "能力发展", skillId: "enablement_workspace", exampleQueries: ["不要基础课，多给实验"],
    tags: ["自然语言交流", "版本"], enabled: true, sortOrder: 64,
    availability: "ready", actionHref: "/tasks", actionLabel: "选择已有任务",
  },
  {
    id: "enablement-project-advice", name: "针对项目制定发展建议",
    description: "从匹配任务的推荐伙伴入口带入项目需求与参考风险。",
    category: "能力发展", skillId: "enablement_workspace", exampleQueries: ["针对这个项目发展伙伴"],
    tags: ["项目", "伙伴发展"], enabled: true, sortOrder: 65,
    availability: "ready", actionHref: "/tasks", actionLabel: "选择项目任务",
  },
  {
    id: "ai-project-partner-recommendation",
    name: "AI项目伙伴推荐",
    description: "根据项目需求推荐最匹配的服务伙伴",
    category: "智能匹配",
    skillId: "partner_match",
    exampleQueries: ["帮我找适合制造行业知识库 Agent 项目的伙伴"],
    tags: ["AI项目", "伙伴推荐", "智能匹配"],
    enabled: true,
    sortOrder: 10,
    availability: "ready",
    actionHref: "/?scene=ai-project-partner-recommendation&prompt=帮我找适合制造行业知识库%20Agent%20项目的伙伴",
    actionLabel: "开始任务",
  },
  {
    id: "find-partner-by-industry",
    name: "按行业找伙伴",
    description: "寻找具有指定行业经验的伙伴",
    category: "智能匹配",
    skillId: "partner_match",
    exampleQueries: ["找有金融 AI 案例的伙伴"],
    tags: ["行业经验", "伙伴寻源", "案例"],
    enabled: true,
    sortOrder: 20,
    availability: "ready",
    actionHref: "/?scene=find-partner-by-industry&prompt=找有金融%20AI%20案例的伙伴",
    actionLabel: "开始任务",
  },
  {
    id: "find-partner-by-capability",
    name: "按能力找伙伴",
    description: "寻找具备指定专业能力的伙伴",
    category: "智能匹配",
    skillId: "partner_match",
    exampleQueries: ["找具备大模型应用开发和数据治理能力的伙伴"],
    tags: ["专业能力", "能力标签", "伙伴寻源"],
    enabled: true,
    sortOrder: 30,
    availability: "ready",
    actionHref: "/?scene=find-partner-by-capability&prompt=找具备大模型应用开发和数据治理能力的伙伴",
    actionLabel: "开始任务",
  },
  {
    id: "partner-capability-query",
    name: "伙伴能力查询",
    description: "在伙伴洞察中查看已有核心能力和能力标签",
    category: "伙伴洞察",
    skillId: "partner_profile",
    exampleQueries: ["XX伙伴有哪些 AI 能力？"],
    tags: ["伙伴资料", "核心能力", "能力标签"],
    enabled: true,
    sortOrder: 40,
    availability: "ready",
    actionHref: "/partners",
    actionLabel: "查询伙伴",
  },
  {
    id: "partner-ai-profile",
    name: "伙伴AI画像",
    description: "在伙伴洞察中查看已有 AI 能力画像",
    category: "伙伴洞察",
    skillId: "partner_capability_analysis",
    exampleQueries: ["查看 XX 伙伴当前的 AI 能力画像"],
    tags: ["AI画像", "能力分析", "伙伴洞察"],
    enabled: true,
    sortOrder: 50,
    availability: "ready",
    actionHref: "/partners",
    actionLabel: "查看画像",
  },
  {
    id: "partner-case-query",
    name: "伙伴案例查询",
    description: "在伙伴洞察中查看已有项目案例和行业实践",
    category: "伙伴洞察",
    skillId: "partner_case_search",
    exampleQueries: ["查看 XX 伙伴在制造行业的项目案例"],
    tags: ["项目案例", "行业实践", "交付证据"],
    enabled: true,
    sortOrder: 60,
    availability: "ready",
    actionHref: "/partners",
    actionLabel: "选择伙伴查询",
  },
  {
    id: "partner-capability-gap-analysis",
    name: "伙伴能力短板分析",
    description: "结合伙伴画像和目标方向，在现有能力发展中分析建议重点",
    category: "能力发展",
    skillId: "partner_gap_analysis",
    exampleQueries: ["XX伙伴承接制造知识库项目有哪些能力短板？"],
    tags: ["能力短板", "差距分析", "发展建议"],
    enabled: true,
    sortOrder: 70,
    availability: "ready",
    actionHref: "/?mode=development",
    actionLabel: "开始分析",
  },
  {
    id: "project-demand-profile",
    name: "项目需求画像",
    description: "将项目需求转化为结构化需求画像",
    category: "运营分析",
    skillId: "demand_profile",
    exampleQueries: ["把这段项目需求整理成结构化需求画像"],
    tags: ["需求画像", "结构化分析", "供需状态"],
    enabled: true,
    sortOrder: 80,
    availability: "embedded",
    actionHref: "/tasks",
    actionLabel: "查看已有画像",
  },
  {
    id: "project-opportunity-identification",
    name: "项目机会识别",
    description: "从需求中识别值得运营跟进的项目机会",
    category: "项目机会",
    skillId: "project_opportunity_extract",
    exampleQueries: ["从当前需求中识别需要重点跟进的项目机会"],
    tags: ["机会识别", "运营跟进", "项目机会"],
    enabled: true,
    sortOrder: 90,
    availability: "embedded",
    actionHref: "/tasks",
    actionLabel: "查看机会库",
  },
  {
    id: "capability-tag-suggestion",
    name: "能力标签建议",
    description: "根据伙伴资料生成能力标签建议",
    category: "能力发展",
    skillId: "capability_tag_suggest",
    exampleQueries: ["根据现有资料生成待采纳的能力标签建议"],
    tags: ["标签建议", "伙伴资料", "人工采纳"],
    enabled: false,
    sortOrder: 100,
    availability: "ready",
    actionLabel: "仅管理员可用",
  },
] as const;

export const ENABLED_SCENES = SCENE_REGISTRY
  .filter((scene) => scene.enabled)
  .sort((a, b) => a.sortOrder - b.sortOrder);
