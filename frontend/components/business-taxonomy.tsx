"use client";
import standard from "../../shared/business-taxonomy.json";
export const INDUSTRIES=standard.industries;
export const REGION_TYPES=standard.region_types;
export type RegionType=keyof typeof REGION_TYPES;
const split=(value:string)=>value.split(/[,，、;/；|\n]+/).map(x=>x.trim()).filter(Boolean);
export function standardValues(value:string,kind:"industry"|"region") {
 const allowed=kind==="industry"?INDUSTRIES:Object.values(REGION_TYPES).flat();
 const aliases:Record<string,string>=standard.aliases[kind];
 return [...new Set(split(value).map(x=>aliases[x]||x).filter(x=>allowed.includes(x)))];
}
export function ClassificationFields({industries,regions,onIndustries,onRegions}:{industries:string;regions:string;onIndustries:(v:string)=>void;onRegions:(v:string)=>void}) {
 function choices(title:string,values:string[],selected:string[],change:(v:string)=>void){return <fieldset className="classification-options"><legend>{title}</legend><div>{values.map(x=><label key={x}><input type="checkbox" checked={selected.includes(x)} onChange={e=>change((e.target.checked?[...selected,x]:selected.filter(v=>v!==x)).join(','))}/>{x}</label>)}</div></fieldset>}
 const selected=standardValues(regions,'region');
 return <div className="classification-fields">{choices('行业经验（多选）',INDUSTRIES,standardValues(industries,'industry'),onIndustries)}
 <div className="classification-regions">{(Object.keys(REGION_TYPES) as RegionType[]).map(region_type=><div key={region_type} data-region-type={region_type}>{choices(region_type==='domestic'?'国内省级区域（多选）':'海外区域（多选）',REGION_TYPES[region_type],selected,onRegions)}</div>)}</div></div>;
}
export function ClassificationFilter({kind,value,onChange,label}:{kind:'industry'|'region';value:string;onChange:(v:string)=>void;label:string}) {
 const options=kind==='industry'?[{name:'行业',values:INDUSTRIES}]:[{name:'国内',values:REGION_TYPES.domestic},{name:'海外',values:REGION_TYPES.overseas}];
 return <label className="classification-filter">{label}<select multiple aria-label={label} value={split(value)} onChange={e=>onChange(Array.from(e.target.selectedOptions,o=>o.value).join(','))}>{options.map(g=><optgroup label={g.name} key={g.name}>{g.values.map(x=><option value={x} key={x}>{x}</option>)}</optgroup>)}</select><small>可多选；取消选择可查看全部</small></label>;
}
export function ClassificationNotice({pending}:{pending?:Record<string,string[]>}){
 const values=[...new Set(Object.values(pending||{}).flat())];
 return values.length?<p className="notice-neutral">待确认分类：{values.join('、')}。原记录保留，暂不用于标准筛选或模型结构化字段。</p>:null;
}
