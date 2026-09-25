import type { ReactNode } from "react";

// Only the prose subset used by advisor replies. React escapes all text; model
// output never becomes HTML, an image, or an executable/link destination.
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*\n]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong> : part);
}
function heading(line: string): string | undefined {
  const match = line.match(/^#{1,6}\s+(.+?)(?:\s+#+)?$/) || line.match(/^【([^】]+)】$/) || line.match(/^\*\*([^*]+)\*\*$/);
  return match?.[1];
}
function item(line: string) {
  return line.match(/^(?:([-*+])|([0-9]+)[.)])\s+(.+)$/);
}

export function AdvisorAnswer({ text }: { text: string }) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n").map(line => line.trim());
  const blocks: ReactNode[] = [];
  for (let i = 0; i < lines.length;) {
    if (!lines[i]) { i++; continue; }
    const start = i, title = heading(lines[i]), first = item(lines[i]);
    if (title) {
      const label = title.replace(/^\*\*(.+)\*\*$/, "$1").replace(/^【(.+)】$/, "$1");
      blocks.push(label === "结论"
        ? <h3 key={start}>{inline(label)}</h3> : <h4 key={start}>{inline(label)}</h4>);
      i++; continue;
    }
    if (first) {
      const ordered = Boolean(first[2]), entries: ReactNode[] = [];
      while (i < lines.length) {
        const next = item(lines[i]);
        if (!next || Boolean(next[2]) !== ordered) break;
        entries.push(<li key={i}>{inline(next[3])}</li>); i++;
      }
      blocks.push(ordered ? <ol key={start} start={Number(first[2])}>{entries}</ol> : <ul key={start}>{entries}</ul>);
      continue;
    }
    const paragraph = [lines[i++]];
    while (i < lines.length && lines[i] && !heading(lines[i]) && !item(lines[i])) paragraph.push(lines[i++]);
    blocks.push(<p key={start}>{inline(paragraph.join("\n"))}</p>);
  }
  return <div className="advisor-answer" data-testid="advisor-answer">
    <p className="advisor-answer-label">伴飞</p>
    <div className="advisor-answer-body">{blocks}</div>
  </div>;
}
