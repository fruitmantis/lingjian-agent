import {redirect} from "next/navigation";
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){
 const input=await searchParams, next=new URLSearchParams();
 const resources=input.tab==="resources";
 for(const key of resources?["resource_type"]:["partner_id","task_id","case_id","case_version"]){const value=input[key];if(typeof value==="string")next.set(key,value);}
 if(!resources)next.set("mode","development");
 redirect(`${resources?"/resources":"/"}?${next}`);
}
