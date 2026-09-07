import {redirect} from "next/navigation";
export default async function Page({params,searchParams}:{params:Promise<{type:string;id:string}>;searchParams:Promise<{source_version?:string}>}){
 const {type,id}=await params,{source_version}=await searchParams;
 redirect(`/resources/${encodeURIComponent(type)}/${encodeURIComponent(id)}${source_version?`?source_version=${encodeURIComponent(source_version)}`:""}`);
}
