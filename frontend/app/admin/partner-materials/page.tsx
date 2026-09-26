import {Suspense} from 'react';
import {PartnerMaterialsManager} from '@/components/partner-materials-manager';
export default function Page(){return <Suspense fallback={<main className="page">正在加载伙伴资料…</main>}><PartnerMaterialsManager/></Suspense>;}
