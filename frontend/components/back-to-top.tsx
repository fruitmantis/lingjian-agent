"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { UiIcon } from "./ui-icons";
import styles from "./back-to-top.module.css";

/** Show the control only after the reader has scrolled past roughly one screen of content. */
const SHOW_AFTER = 480;

export function BackToTop() {
  const [visible, setVisible] = useState(false);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const update = () => {
      frame.current = null;
      setVisible(window.scrollY > SHOW_AFTER);
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
    };
  }, []);

  const toTop = useCallback(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    window.scrollTo({ top: 0, left: 0, behavior: reduce ? "auto" : "smooth" });
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
