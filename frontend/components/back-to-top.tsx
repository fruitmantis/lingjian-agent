"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { UiIcon } from "./ui-icons";
import styles from "./back-to-top.module.css";

/** Show the control only after the reader has scrolled past roughly one screen of content. */
const SHOW_AFTER = 480;
/** Never chase a smooth scroll for longer than this. */
const MAX_SETTLE_MS = 1500;
/** Consecutive frames without movement that count as "the animation is done". */
const STUCK_FRAMES = 20;

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
  const poll = useRef<number | null>(null);
  // Cached once per layout: querying and measuring on every scroll frame forces a reflow.
  const scrollers = useRef<HTMLElement[]>([]);

  useEffect(() => {
    const measure = () => { scrollers.current = pageScrollers(); };
    const update = () => {
      frame.current = null;
      const top = Math.max(window.scrollY, ...scrollers.current.map(element => element.scrollTop));
      setVisible(top > SHOW_AFTER);
    };
    const schedule = () => {
      if (frame.current === null) frame.current = window.requestAnimationFrame(update);
    };
    const onResize = () => { measure(); schedule(); };
    measure();
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", onResize);
    const remeasure = window.setTimeout(measure, 1000);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", onResize);
      window.clearTimeout(remeasure);
      if (frame.current !== null) window.cancelAnimationFrame(frame.current);
      if (poll.current !== null) window.cancelAnimationFrame(poll.current);
    };
  }, []);

  const toTop = useCallback(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const behavior: ScrollBehavior = reduce ? "auto" : "smooth";
    const finish = () => {
      if (poll.current !== null) { window.cancelAnimationFrame(poll.current); poll.current = null; }
      if (window.scrollY > 0) window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      for (const element of pageScrollers()) if (element.scrollTop > 0) element.scrollTop = 0;
    };
    const distance = Math.max(window.scrollY, ...scrollers.current.map(element => element.scrollTop));
    // Animating thousands of pixels over a heavy page is what reads as a stutter,
    // so long jumps land immediately; only short ones keep the smooth motion.
    if (reduce || distance > window.innerHeight * 2) { finish(); return; }
    window.scrollTo({ top: 0, left: 0, behavior });
    for (const element of scrollers.current) element.scrollTo({ top: 0, left: 0, behavior });
    // Wait for the animation to actually stop instead of cutting it off with a fixed timer,
    // which is what read as a stutter on tall pages.
    if (poll.current !== null) window.cancelAnimationFrame(poll.current);
    const deadline = performance.now() + MAX_SETTLE_MS;
    let previous = -1;
    let still = 0;
    const step = () => {
      const y = window.scrollY;
      if (y === 0 || performance.now() > deadline) { finish(); return; }
      still = y === previous ? still + 1 : 0;
      previous = y;
      if (still > STUCK_FRAMES) { finish(); return; }
      poll.current = window.requestAnimationFrame(step);
    };
    poll.current = window.requestAnimationFrame(step);
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
