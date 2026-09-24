"""Bounded real-model scope regression: 32 synthetic decisions, no business writes.

Requires --execute. Reuses current scene bindings read-only; does not generate any
recommendations/advice or read partner/resource data. Reports actual token usage.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OFF_TOPIC = ['明天天气怎么样？', '帮我安排三天旅游行程', '写一个 Python 快速排序函数', '写一首关于月亮的诗']
POSITIVE = {
    'partner_match': [('需要找伙伴，具体需求还没想清楚', ''), ('为什么推荐这个伙伴？', '寻找数据库迁移交付伙伴'),
                      ('旅游平台项目需要开发交付伙伴，顺便问下天气', ''), ('再具体一点', '寻找云平台迁移伙伴')],
    'partner_development': [('伙伴下一步可以发展什么方向？', ''), ('为什么建议先做这个？', '伙伴数据库迁移能力发展'),
                            ('想提升伙伴 Python 项目交付能力，顺便写首诗', ''), ('只看实验，不要基础课', '伙伴云应用交付能力发展')],
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args=parser.parse_args()
    if not args.execute:parser.error('--execute required; no request sent')
    fd=os.open(args.output, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600);os.close(fd)
    os.environ.update(json.loads(args.environment.read_text()))
    # Test faults must not pollute the runtime's recent errors.
    os.environ['BANFEI_ERROR_LOG_PATH']=str(args.output.with_suffix('.errors.jsonl'))
    from backend.app import scope_gate as gate, development_model as model
    from backend.app.error_diagnostics import diagnostic_scope
    resolve=gate.resolve_model_config;configuration=model.configuration
    gate.resolve_model_config=lambda scene:resolve(scene,read_only=True)
    model.configuration=lambda:configuration(read_only=True)
    report={'kind':'real-scope-gate-regression','max_requests':32,'calls':[],'checks':[]}
    def save():args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    original=model.httpx.AsyncClient
    class AuditedClient(original):
        async def send(self,request,**kwargs):
            if len(report['calls'])>=32:raise RuntimeError('Scope regression request budget exceeded')
            item={'provider':urlsplit(str(request.url)).hostname,'model':json.loads(request.content)['model'],
                  'time':datetime.now(timezone.utc).isoformat(),'case':report['case']}
            report['calls'].append(item);save();start=time.monotonic()
            try:
                response=await super().send(request,**kwargs)
                item['http_status']=response.status_code
                if response.is_success:item['usage']=response.json().get('usage')
                return response
            finally:item['seconds']=round(time.monotonic()-start,3);save()
    model.httpx.AsyncClient=AuditedClient
    try:
        for mode in ('partner_match','partner_development'):
            cases=[(text,'',False) for text in OFF_TOPIC for _ in range(3)]+[(text,context,True) for text,context in POSITIVE[mode]]
            for index,(text,context,expected) in enumerate(cases):
                report['case']=f'{mode}:{index+1}'
                item={'mode':mode,'input':text,'context':context,'expected':expected}
                try:
                    with diagnostic_scope(stage='scope_gate'):
                        item['actual']=gate.check(mode,text,context=context)
                    item['passed']=item['actual'] is expected
                except Exception as error:item.update(passed=False,error_type=type(error).__name__)
                report['checks'].append(item);save()
                print(json.dumps({'case':report['case'],'passed':item['passed']},ensure_ascii=False),flush=True)
    finally:
        model.httpx.AsyncClient=original;gate.resolve_model_config=resolve;model.configuration=configuration
    report['result']='PASS' if len(report['checks'])==32 and all(item['passed'] for item in report['checks']) else 'FAIL'
    save()
    print(json.dumps({'result':report['result'],'requests':len(report['calls']),'passed':sum(item['passed'] for item in report['checks']),'report':str(args.output)}))
    return 0 if report['result']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
