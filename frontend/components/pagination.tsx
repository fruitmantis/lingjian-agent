"use client";

import { useEffect, useId, useState } from "react";

type PaginationProps = {
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  label?: string;
  pageSizeOptions?: readonly number[];
  onPageSizeChange?: (size: number) => void;
};

/** One paging control for remote lists and local slices; callers retain their filters. */
export function Pagination({ page, total, pageSize, onPageChange, disabled = false,
  label = "列表分页", pageSizeOptions, onPageSizeChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(Math.max(1, page), totalPages);
  const [target, setTarget] = useState(String(currentPage));
  const [error, setError] = useState("");
  const errorId = useId();

  useEffect(() => { setTarget(String(currentPage)); setError(""); }, [currentPage, totalPages]);
  useEffect(() => {
    // A refreshed or filtered list may have fewer pages than the previous response.
    if (!disabled && page !== currentPage) onPageChange(currentPage);
  }, [page, currentPage, disabled, onPageChange]);

  function jump() {
    if (disabled || totalPages <= 1) return;
    const value = target.trim(), next = Number(value);
    if (!/^\d+$/.test(value) || !Number.isSafeInteger(next) || next < 1 || next > totalPages) {
      setError(`请输入 1～${totalPages} 之间的整数页码。`);
      return;
    }
    setError(""); setTarget(String(next));
    if (next !== page) onPageChange(next);
  }

  return <nav className="pagination" aria-label={label} aria-busy={disabled}>
    <div className="pagination-summary">
      <span>共 {total} 条</span>
      {pageSizeOptions && onPageSizeChange && <label>每页
        <select aria-label="每页条数" value={pageSize} disabled={disabled}
          onChange={event => onPageSizeChange(Number(event.target.value))}>
          {pageSizeOptions.map(size => <option key={size} value={size}>{size}</option>)}
        </select>条
      </label>}
    </div>
    <div className="pagination-controls">
      <button type="button" className="secondary-btn" disabled={disabled || currentPage <= 1}
        onClick={() => onPageChange(currentPage - 1)}>上一页</button>
      <span className="pagination-position" aria-live="polite">第 <strong>{currentPage}</strong> 页 / 共 <strong>{totalPages}</strong> 页</span>
      <button type="button" className="secondary-btn" disabled={disabled || currentPage >= totalPages}
        onClick={() => onPageChange(currentPage + 1)}>下一页</button>
      <form className="pagination-jump" noValidate onSubmit={event => { event.preventDefault(); jump(); }}>
        <label>前往<input aria-label="跳转页码" type="text" inputMode="numeric" maxLength={9}
          value={target} disabled={disabled || totalPages <= 1} aria-invalid={!!error}
          aria-describedby={error ? errorId : undefined}
          onChange={event => { setTarget(event.target.value); setError(""); }} />页</label>
        <button type="submit" className="secondary-btn" disabled={disabled || totalPages <= 1}>跳转</button>
      </form>
    </div>
    {error && <p id={errorId} role="alert" className="pagination-error">{error}</p>}
  </nav>;
}
