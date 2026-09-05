"use client";
import { useParams } from 'next/navigation';
import { CaseSharingManager } from '../../../../../../../components/enablement-admin';
export default function SharingPage(){const params=useParams<{id:string;caseId:string}>();return <CaseSharingManager caseId={params.caseId} partnerId={params.id}/>;}
