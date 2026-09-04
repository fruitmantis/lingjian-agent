"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ENABLED_SCENES, SCENE_CATEGORIES } from "@/lib/scenes";
import { SKILLS_BY_ID } from "@/lib/skills";

type CategoryFilter = (typeof SCENE_CATEGORIES)[number];

const STATUS_TEXT = {
  ready: "可使用",
  embedded: "随匹配生成",
  building: "能力建设中",
} as const;

export default function ScenesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedCategory = searchParams.get("category");
  const initialCategory = SCENE_CATEGORIES.includes(requestedCategory as CategoryFilter)
    ? requestedCategory as CategoryFilter
    : "全部";
  const [category, setCategory] = useState<CategoryFilter>(initialCategory);
  const [keyword, setKeyword] = useState("");

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
        <div>
          <p className="scenes-kicker">SCENE GALLERY</p>
          <h1>场景广场</h1>
          <p>从具体业务任务开始，调用灵鉴已有的伙伴、能力与项目服务。</p>
        </div>
        <div className="scenes-summary" aria-label="场景概览">
          <strong>{ENABLED_SCENES.length}</strong>
          <span>个首批场景</span>
        </div>
      </section>

      <section className="scene-toolbar" aria-label="场景筛选">
        <div className="scene-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" /></svg>
          <label htmlFor="scene-search" className="sr-only">搜索场景</label>
          <input id="scene-search" type="search" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索场景名称、描述或标签" />
          {keyword && <button type="button" onClick={() => setKeyword("")} aria-label="清空搜索">×</button>}
        </div>
        <div className="scene-category-tabs" role="tablist" aria-label="场景分类">
          {SCENE_CATEGORIES.map((item) => (
            <button key={item} type="button" role="tab" aria-selected={category === item} className={category === item ? "active" : ""} onClick={() => selectCategory(item)}>{item}</button>
          ))}
        </div>
      </section>

      <div className="scene-result-summary">
        <span>{category === "全部" ? "全部场景" : category}</span>
        <small>找到 {filteredScenes.length} 个场景</small>
      </div>

      {filteredScenes.length > 0 ? (
        <section className="scene-gallery-grid" aria-live="polite">
          {filteredScenes.map((scene) => {
            const skill = SKILLS_BY_ID[scene.skillId];
            return (
              <article className={`scene-gallery-card ${scene.availability}`} key={scene.id}>
                <div className="scene-gallery-copy">
                  <div className="scene-gallery-meta">
                    <span className="scene-category-label">{scene.category}</span>
                    <span className={`availability-badge ${scene.availability}`}>{STATUS_TEXT[scene.availability]}</span>
                  </div>
                  <h2>{scene.name}</h2>
                  <p>{scene.description}</p>
                </div>
                <div className="scene-example">
                  <span>示例问题</span>
                  <p>“{scene.exampleQueries[0]}”</p>
                </div>
                <div className="scene-gallery-tags">{scene.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
                <div className="scene-skill-reference">
                  <span>复用能力</span>
                  <code>{skill.id}</code>
                </div>
                {scene.actionHref ? (
                  <Link href={scene.actionHref} className="scene-card-action">{scene.actionLabel}<span aria-hidden="true">→</span></Link>
                ) : (
                  <span className="scene-card-action disabled" aria-disabled="true">{scene.actionLabel}<span aria-hidden="true">—</span></span>
                )}
              </article>
            );
          })}
        </section>
      ) : (
        <section className="scene-empty">
          <span aria-hidden="true">⌕</span>
          <h2>没有找到匹配场景</h2>
          <p>试试更换关键词或查看全部分类。</p>
          <button type="button" onClick={() => { setKeyword(""); selectCategory("全部"); }}>查看全部场景</button>
        </section>
      )}
    </main>
  );
}
