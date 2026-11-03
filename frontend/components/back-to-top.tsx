"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { UiIcon } from "./ui-icons";
import styles from "./back-to-top.module.css";

/** Show the control only after the reader has scrolled past roughly one screen of content. */
const SHOW_AFTER = 480;
/** Give the smooth animation time to finish before forcing the real top. */
const SETTLE_MS = 600;

/** Every element that can actually hold the page scroll position in this layout. */
function pageScrollers(): HTMLElement[] {
  const found = new Set<HTMLElement>();
  const root = document.scrollingElement as HTMLElement | null;
  if (root) found.add(root);
  found.add(document.documentElement);
  document
    .querySelectorAll<HTMLElement>(".main-area, .page-content, main, [data-page-scroll]")
    .forEach(element => found.add(element));
  return Array.from(found).filter(element => element.scrollHeight - element.clientHeight > 1);
}

export function BackToTop() {
  const [visible, setVisible] = useState(false);
  const frame = useRef<number | null>(null);
  const settle = useRef<number | null>(null);

  useEffect(() => {
    const update = () => {
      frame.current = null;
      const top = Math.max(window.scrollY, ...pageScrollers().map(element => element.scrollTop));
      setVisible(top > SHOW_AFTER);
    };
    const schedule = () => {
      if (frame.current === null) frame.current = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      if (frame.current !== null) window.cancelAnimationFrame(frame.current);
      if (settle.current !== null) window.clearTimeout(settle.current);
    };
  }, []);

  const toTop = useCallback(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const behavior: ScrollBehavior = reduce ? "auto" : "smooth";
    const scrollers = pageScrollers();
    window.scrollTo({ top: 0, left: 0, behavior });
    for (const element of scrollers) element.scrollTo({ top: 0, left: 0, behavior });
    if (reduce) return;
    // A smooth scroll can stop short when content above finishes loading mid-animation,
    // so settle on the real top once it has had time to run.
    if (settle.current !== null) window.clearTimeout(settle.current);
    settle.current = window.setTimeout(() => {
      settle.current = null;
      if (window.scrollY > 0) window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      for (const element of pageScrollers()) if (element.scrollTop > 0) element.scrollTop = 0;
    }, SETTLE_MS);
  }, []);

  return <button
    type="button"
    className={`${styles.button} ${visible ? styles.visible : ""}`}
    aria-label="回到顶部"
    title="回到顶部"
    aria-hidden={!visible}
    tabIndex={visible ? 0 : -1}
    onClick={toTop}
  ><UiIcon name="arrow-up" size={20} /></button>;
}
