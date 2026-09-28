"use client";

import { memo, useLayoutEffect, useMemo, useRef, useState } from "react";

type PartnerTagListProps = {
  value: string | null;
  label: string;
  emptyText: string;
  compact?: boolean;
};

/** Retain tag order and names, including spaces and slashes. */
export function splitPartnerTags(value: string | null) {
  return (value || "").split(/[,，、;；\n]+/).map(tag => tag.trim()).filter(Boolean);
}

export const PartnerTagList = memo(function PartnerTagList({ value, label, emptyText, compact = false }: PartnerTagListProps) {
  const tags = useMemo(() => splitPartnerTags(value), [value]);

  if (!tags.length) return <p className="partner-tag-empty">{emptyText}</p>;
  if (compact) return <CompactPartnerTags tags={tags} label={label} />;

  return (
    <ul className="partner-tag-list" aria-label={label} role="list">
      {tags.map((tag, index) => <li key={`${index}-${tag}`}>{tag}</li>)}
    </ul>
  );
});

function CompactPartnerTags({ tags, label }: { tags: string[]; label: string }) {
  const listRef = useRef<HTMLUListElement>(null);
  const measurementsRef = useRef<HTMLDivElement>(null);
  const counterRef = useRef<HTMLSpanElement>(null);
  const [visibleCount, setVisibleCount] = useState(0);

  useLayoutEffect(() => {
    const list = listRef.current!, measurements = measurementsRef.current!, counter = counterRef.current!;
    let active = true, frame = 0, lastWidth = -1;
    function measure() {
      if (!active) return;
      const available = list.getBoundingClientRect().width;
      const gap = parseFloat(getComputedStyle(list).columnGap) || 0;
      const widths = Array.from(measurements.querySelectorAll<HTMLElement>('[data-tag-measure]'), tag => tag.getBoundingClientRect().width);
      const total = widths.reduce((sum, width) => sum + width, 0) + gap * (widths.length - 1);
      if (total <= available) { setVisibleCount(tags.length); return; }

      let count = 0, used = 0;
      for (let index = 0; index < widths.length - 1; index++) {
        used += widths[index] + (index ? gap : 0);
        counter.textContent = `+${tags.length - index - 1} 个${label}`;
        if (used + gap + counter.getBoundingClientRect().width > available) break;
        count = index + 1;
      }
      setVisibleCount(count);
    }
    // Filter updates keep unchanged tag lists stable. Coalesce font/resize signals into one frame.
    function scheduleMeasure() {
      if (!active) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    }
    scheduleMeasure();
    const observer = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect.width;
      if (width !== undefined && width !== lastWidth) { lastWidth = width; scheduleMeasure(); }
    });
    observer.observe(list);
    void document.fonts.ready.then(scheduleMeasure);
    document.fonts.addEventListener('loadingdone', scheduleMeasure);
    return () => { active = false; cancelAnimationFrame(frame); observer.disconnect(); document.fonts.removeEventListener('loadingdone', scheduleMeasure); };
  }, [tags, label]);

  const hiddenCount = tags.length - visibleCount;
  return (
    <div className="partner-tag-row">
      <ul ref={listRef} className="partner-tag-list is-compact" aria-label={label} role="list">
        {tags.slice(0, visibleCount).map((tag, index) => <li key={`${index}-${tag}`} data-partner-tag="">{tag}</li>)}
        {hiddenCount > 0 && <li className="partner-tag-count" aria-label={`另有 ${hiddenCount} 个${label}，进入伙伴详情查看全部`}>+{hiddenCount} 个{label}</li>}
      </ul>
      {/* Measurement nodes stay outside the accessible list and never change accessibility state. */}
      <div ref={measurementsRef} className="partner-tag-measurements" aria-hidden="true" inert>
        {tags.map((tag, index) => <span data-tag-measure="" key={`${index}-${tag}`}>{tag}</span>)}
        <span ref={counterRef} />
      </div>
    </div>
  );
}
