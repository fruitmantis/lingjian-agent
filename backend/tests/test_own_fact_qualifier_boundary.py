"""Legal output contracts; fixed responses do not measure model semantic quality."""
import pytest
from .test_independent_match_p1 import setup, upload, run_actual_task, literal_item

@pytest.mark.parametrize('model_kind,formal',[('planning_only',False),('current_capability',True)])
def test_own_fact_qualifier_is_sent_and_model_category_is_not_reclassified(setup,monkeypatch,model_kind,formal):
    body='该能力处于规划阶段，尚未交付。\n具备药物研发能力。'
    upload(setup,'synthetic-own-fact-planning.txt',body)
    result,payload=run_actual_task(setup,monkeypatch,'需要药物研发服务伙伴',
        lambda c:literal_item(c,model_kind,'相关能力自述（待核实）：具备药物研发能力。','具备药物研发能力。'))
    assert any(body in p['text'] for c in payload['candidates'] if c['partnerId']==setup[3] for p in c['profilePassages']), 'The qualifier must still reach the provider-shaped payload'
    # planning_only is excluded; deliberately wrong current_capability remains a
    # model judgment, not an invitation to add a program semantic veto.
    assert bool(result['recommendations']) is formal
    assert result['supplyStatus']==('sufficient' if formal else 'unknown')
    if not formal:
        assert '未来规划线索' in result['answer']
