export type DraftContext={partner_id?:string;task_id?:string;case_id?:string;case_version?:string};
export type ModelDraft={text?:string;modelConfigId?:string;context?:DraftContext;openMenu?:boolean};
export const draftKey=(userId:string,agent:string,scope="draft")=>`banfei:model-draft:${userId}:${agent}:${scope}`;
export function readModelDraft(userId:string,agent:string,scope="draft"):ModelDraft{
 try{const value=JSON.parse(sessionStorage.getItem(draftKey(userId,agent,scope))||"{}");return value&&typeof value==="object"&&!Array.isArray(value)?value:{};}catch{return {};}
}
export function saveModelDraft(userId:string,agent:string,value:ModelDraft,scope="draft"){
 try{sessionStorage.setItem(draftKey(userId,agent,scope),JSON.stringify({...readModelDraft(userId,agent,scope),...value}));}catch{/* The current page still retains its draft. */}
}
export function clearModelDraft(userId:string,agent:string,scope="draft"){
 try{sessionStorage.removeItem(draftKey(userId,agent,scope));}catch{/* Optional session persistence. */}
}
