"use client";
import { use } from "react";
import { ResourceDetail } from "@/components/enablement-workspace";
export default function Page({params}:{params:Promise<{type:string;id:string}>}){const {type,id}=use(params);return <ResourceDetail key={`${type}:${id}`} type={type} id={id}/>;}
