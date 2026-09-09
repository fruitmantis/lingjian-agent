"""Explicit, two-request synthetic supplier smoke; no business data is read or written.

Uses the production development adapter/schema. Does not prove business acceptance.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment',type=Path,required=True,help='Private runtime environment JSON; read only')
    parser.add_argument('--model-config-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stage',choices=['both','analyze','plan'],default='both')
    parser.add_argument('--execute',action='store_true',help='Explicitly authorize up to two synthetic requests')
    args=parser.parse_args()
    if not args.execute:parser.error('--execute is required; no model request sent')
    # Reserve the audit file before any request; no overwrite of previous evidence.
    fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    os.environ.update(json.loads(args.environment.read_text()))
    from backend.app.database import get_readonly_db
    from backend.app import development_model, development_engine
    from backend.app.development_types import DirectionAnalysis, AdviceOutput
    with get_readonly_db() as conn:
        row=conn.execute('SELECT * FROM model_configs WHERE id=? AND enabled=1',(args.model_config_id,)).fetchone()
        if not row:raise SystemExit('Selected model is not enabled')
        config=dict(row)
    config['max_tokens']=4096  # Smoke-only budget; saved configuration is unchanged.
    report={'kind':'real-provider-synthetic-smoke','max_calls':2,'calls':[],'business_acceptance':'NOT RUN'}
    import httpx
    original=development_model.httpx.AsyncClient
    class AuditedClient(original):
        async def send(self,request,**kwargs):
            if len(report['calls'])>=2:raise RuntimeError('Synthetic smoke budget exceeded')
            item={'provider':urlsplit(str(request.url)).hostname,'model':config['model_name'],
                  'timestamp':datetime.now(timezone.utc).isoformat(),'scenario':report['scenario'],'status':'started'}
            report['calls'].append(item)
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            started=time.monotonic()
            try:
                response=await super().send(request,**kwargs)
                item['http_status']=response.status_code
                item['status']='received' if response.is_success else 'http_error'
                if response.is_success:item['usage']=response.json().get('usage')
                return response
            except Exception as error:
                item['status']=type(error).__name__
                raise
            finally:
                item['latency_seconds']=round(time.monotonic()-started,3)
                args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    development_model.httpx.AsyncClient=AuditedClient
    request={'target_partner_id':'synthetic-smoke-partner','development_direction':'合成连通性测试：希望了解 Agent 应用集成能力方向。简短回答。'}
    try:
        for stage,contract,payload in [
            ('analyze',DirectionAnalysis,{'request':request,'profile':{'summary':'合成测试伙伴，具有应用开发基础，没有已确认能力结论。'},'formal_tags':[]}),
            ('plan',AdviceOutput,{'request':request,'analysis':{'intent':'development','priorities':[]},'candidates':[]})]:
            if args.stage!='both' and args.stage!=stage:continue
            report['scenario']=stage
            output=development_engine.call(config,stage,payload,contract,[])
            assert output['target_partner_id']==request['target_partner_id']
            if stage=='analyze':
                assert all(not item.get('capability_tag_id') for item in output['priorities'])
            else:
                assert not any(s['items'] for s in output['stages']), 'Empty candidates must not produce resources'
            report['calls'][-1]['validation']='PASS'
        report['result']='PASS'
    except Exception as error:
        report['result']='FAIL'
        report['safe_error_type']=type(error).__name__
    finally:
        development_model.httpx.AsyncClient=original
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['result']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
