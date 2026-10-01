import type {ReactNode} from 'react';
import styles from './partner-profile-report.module.css';

const separator = (line:string) => /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
function cells(line:string):string[] {
  const text=line.trim().replace(/^\|/,'').replace(/\|$/,'');
  const result:string[]=[];let value='';
  for(let i=0;i<text.length;i++) {
    if(text[i]==='\\' && (text[i+1]==='|' || text[i+1]==='\\'))value+=text[++i];
    else if(text[i]==='|'){result.push(value.trim());value='';}
    else value+=text[i];
  }
  result.push(value.trim());return result.map(v=>v.replace(/<br\s*\/?>/g,'\n'));
}
function heading(line:string) {
  const markdown=line.match(/^\s*(#{1,6})\s+(.+)$/);
  if(markdown)return {text:markdown[2],major:markdown[1].length<=2};
  if(/^[一二三四五六七八九十]+、/.test(line))return {text:line,major:true};
  return null;
}
function inline(text:string):ReactNode[] {
  return text.split(/(\*\*[^*\n]+\*\*)/g).map((s,i)=>s.startsWith('**')&&s.endsWith('**')?<strong key={i}>{s.slice(2,-2)}</strong>:s);
}

// Deliberately render text with React; no raw HTML, images, or model-supplied links.
export function PartnerProfileReport({text}:{text:string}) {
  const lines=text.replace(/\r\n?/g,'\n').split('\n');const blocks:ReactNode[]=[];
  for(let i=0;i<lines.length;) {
    const start=i;
    if(!lines[i].trim()){i++;continue;}
    const title=heading(lines[i]);
    if(title){blocks.push(title.major?<h3 key={i}>{inline(title.text)}</h3>:<h4 key={i}>{inline(title.text)}</h4>);i++;continue;}
    const markdown=lines[i].includes('|') && separator(lines[i+1]||'');
    const native=lines[i].includes('\t');
    if(markdown||native) {
      const rows:string[][]=[];
      rows.push(markdown?cells(lines[i]):lines[i].split('\t'));i+=markdown?2:1;
      while(i<lines.length && lines[i].trim() && (markdown?lines[i].includes('|'):lines[i].includes('\t'))){rows.push(markdown?cells(lines[i]):lines[i].split('\t'));i++;}
      blocks.push(<div className={styles.tableWrap} key={start}><table><thead><tr>{rows[0].map((cell,j)=><th scope="col" key={j}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.slice(1).map((row,n)=><tr key={n}>{row.map((cell,j)=><td key={j}>{inline(cell)}</td>)}</tr>)}</tbody></table></div>);continue;
    }
    const paragraph=[lines[i++]];
    while(i<lines.length && lines[i].trim() && !heading(lines[i]) && !lines[i].includes('\t') && !(lines[i].includes('|')&&separator(lines[i+1]||'')))paragraph.push(lines[i++]);
    blocks.push(<p key={start}>{inline(paragraph.join('\n'))}</p>);
  }
  return <article className={styles.report} data-testid="partner-profile-report">{blocks}</article>;
}
