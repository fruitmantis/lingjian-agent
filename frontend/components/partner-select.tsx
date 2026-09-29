"use client";

import {useEffect, useId, useLayoutEffect, useRef, useState} from "react";
import {createPortal} from "react-dom";
import styles from "./partner-select.module.css";

type Partner = {id: string; name: string};
type Position = {left: number; width: number; top?: number; bottom?: number; maxHeight: number};

/** Search only the caller's authorized choices; typing never changes the selected ID. */
export function PartnerSelect({partners, value, onChange, label, caption, placeholder = "请选择伙伴", disabled = false, required = false, className = ""}: {
  partners: Partner[]; value: string; onChange: (id: string) => void; label: string;
  caption?: string; placeholder?: string; disabled?: boolean; required?: boolean; className?: string;
}) {
  const id = useId(), listId = `${id}-options`;
  const root = useRef<HTMLDivElement>(null), popup = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false), [query, setQuery] = useState(""), [active, setActive] = useState(0);
  const [position, setPosition] = useState<Position | null>(null);
  const needle = query.trim().toLocaleLowerCase();
  const choices = [...(!required && !needle ? [{id: "", name: placeholder}] : []), ...partners.filter(p => p.name.toLocaleLowerCase().includes(needle))];
  const selected = partners.find(p => p.id === value);
  const expanded = open && !disabled;
  const activeIndex = Math.min(active, choices.length - 1);
  useEffect(() => {setOpen(false); setQuery("");}, [value, disabled]);

  function show() {
    if (disabled || open) return;
    setQuery(""); setActive(Math.max(0, partners.findIndex(p => p.id === value) + (required ? 0 : 1))); setOpen(true);
  }
  function choose(partnerId: string) {
    onChange(partnerId); setOpen(false); setQuery("");
    // Options retain input focus on mouse down; touch selection may move it.
    input.current?.focus({preventScroll: true});
  }
  useEffect(() => {
    if (!expanded) return;
    const dismiss = (event: Event) => {
      const target = event.target as Node;
      if (!root.current?.contains(target) && !popup.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss, true);
    document.addEventListener("focusin", dismiss, true);
    return () => { document.removeEventListener("pointerdown", dismiss, true); document.removeEventListener("focusin", dismiss, true); };
  }, [expanded]);
  useLayoutEffect(() => {
    if (!expanded) return;
    function align() {
      const bounds = input.current?.getBoundingClientRect();
      if (!bounds) return;
      const below = window.innerHeight - bounds.bottom - 12, above = bounds.top - 12;
      const upwards = below < 240 && above > below;
      const next: Position = {left: Math.max(8, Math.min(bounds.left, window.innerWidth - bounds.width - 8)), width: Math.min(bounds.width, window.innerWidth - 16), maxHeight: Math.max(80, Math.min(320, upwards ? above : below)), ...(upwards ? {bottom: window.innerHeight - bounds.top + 4} : {top: bounds.bottom + 4})};
      setPosition(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    }
    align(); window.addEventListener("resize", align); window.addEventListener("scroll", align, true);
    return () => { window.removeEventListener("resize", align); window.removeEventListener("scroll", align, true); };
  }, [expanded]);
  useEffect(() => {
    if (expanded) document.getElementById(`${id}-option-${activeIndex}`)?.scrollIntoView({block: "nearest"});
  }, [expanded, activeIndex, needle, id, position !== null]);

  return <div ref={root} className={`${styles.root} ${className}`}>
    {caption && <label className={styles.caption} htmlFor={id}>{caption}</label>}
    <div className={styles.control}>
      <input ref={input} id={id} className={styles.input} role="combobox" aria-label={label} aria-autocomplete="list" aria-expanded={expanded} aria-controls={expanded ? listId : undefined} aria-activedescendant={expanded && choices.length ? `${id}-option-${activeIndex}` : undefined} aria-required={required || undefined} autoComplete="off" disabled={disabled} data-partner-id={value}
        value={expanded ? query : selected?.name || (value ? "当前伙伴暂不可选" : "")} placeholder={expanded ? "输入伙伴名称搜索" : placeholder}
        onFocus={show} onClick={show} onChange={event => {setQuery(event.target.value); setActive(0); setOpen(true);}}
        onKeyDown={event => {
          if (event.nativeEvent.isComposing || event.keyCode === 229) return;
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!expanded) show(); else setActive(index => Math.max(0, Math.min(choices.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
          } else if (event.key === "Enter" && expanded) {event.preventDefault(); if (choices[activeIndex]) choose(choices[activeIndex].id);}
          else if (event.key === "Escape" && expanded) {event.preventDefault(); event.stopPropagation(); setOpen(false);}
          else if (event.key === "Tab") setOpen(false);
        }}/>
      <button type="button" className={styles.toggle} tabIndex={-1} disabled={disabled} aria-label={`${expanded ? "收起" : "展开"}${label}`} onMouseDown={event => event.preventDefault()} onClick={() => {if (expanded) setOpen(false); else {show(); input.current?.focus();}}}>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg>
      </button>
    </div>
    {expanded && position && createPortal(<div ref={popup} className={styles.popup} style={position}>
      <div className={styles.count} role="status">{needle ? `找到 ${choices.length} 家伙伴` : `共 ${partners.length} 家伙伴，可输入名称查找`}</div>
      <div id={listId} role="listbox" aria-label={`${label}选项`} className={styles.options}>
        {choices.map((partner, index) => <button key={partner.id} id={`${id}-option-${index}`} type="button" role="option" aria-selected={value === partner.id} data-partner-id={partner.id} tabIndex={-1} className={`${styles.option} ${index === activeIndex ? styles.highlighted : ""}`} onMouseDown={event => event.preventDefault()} onClick={() => choose(partner.id)}>
          <span>{partner.name}</span>{value === partner.id && <span aria-hidden="true">✓</span>}
        </button>)}
      </div>
      {!choices.length && <p className={styles.empty}>没有匹配的伙伴，请换个名称试试。</p>}
    </div>, document.body)}
  </div>;
}
