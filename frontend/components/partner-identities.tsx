"use client";
import identities from "../../shared/partner-identities.json";
import {PartnerTagList} from "./partner-tag-list";

export function PartnerIdentityFields({value,onChange,disabled=false}:{value:string[];onChange:(value:string[])=>void;disabled?:boolean}){
  return <fieldset className="classification-options form-span-two" disabled={disabled}>
    <legend>伙伴身份（多选）</legend>
    <div>{identities.map(name=><label key={name}><input type="checkbox" checked={value.includes(name)} onChange={event=>onChange(event.target.checked?[...value,name]:value.filter(item=>item!==name))}/><span>{name}</span></label>)}</div>
  </fieldset>;
}

export function PartnerIdentityList({value}:{value?:string[]}){
  if(!value?.length)return null;
  return <div data-testid="partner-identities"><PartnerTagList value={value.join(',')} label="伙伴身份" emptyText=""/></div>;
}
