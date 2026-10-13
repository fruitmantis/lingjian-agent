"""Normal exclusions are distinct from missing input or failed evidence checks."""
import pytest
from backend.app.database import get_db
from backend.app.routers import match
from .conftest import make_partner, recommendation
from .test_profile_report import setup


@pytest.mark.parametrize('scenario,keep_current,complete', [
    ('mixed', True, True),
    ('all_unrelated', False, True),
    ('missing_core', True, False),
    ('failed_source', True, False),
    ('incomplete_catalogue', True, True),
    ('unsupported_claim', False, False),
])
def test_normal_unrelated_filter_preserves_real_incompleteness(setup, scenario, keep_current, complete):
    other_id = make_partner('unrelated-synthetic-partner')['id']
    with get_db() as conn:
        conn.execute('UPDATE partners SET name=?,capabilities=? WHERE id=?', ('相关合成伙伴', '', setup[3]))
        conn.execute('UPDATE partners SET name=?,capabilities=? WHERE id=?', ('办公合成伙伴', '', other_id))
        partners = [dict(conn.execute('SELECT * FROM partners WHERE id=?', (pid,)).fetchone()) for pid in (setup[3], other_id)]
    rows, items = [], []
    for index, partner in enumerate(partners):
        quote = '具备ScopeQuasar能力。' if index == 0 else '已交付ScopeOther办公平台。'
        source = f"partner:{partner['id']}:profile:0"
        coverage = {'complete': True, 'omittedCoreGroups': 0, 'sourceState': 'ready'}
        if index == 0 and scenario in ('missing_core', 'failed_source'):
            coverage.update(complete=False)
            if scenario == 'missing_core':
                coverage['omittedCoreGroups'] = 1
            else:
                coverage['sourceState'] = 'failed'
        with get_db() as conn:conn.execute('UPDATE partners SET capabilities=? WHERE id=?',(quote,partner['id']))
        mapping={source:{'partnerId':partner['id'],'sourceRef':'partner:'+partner['id'],'path':'/capabilities','start':0,'end':len(quote),'text':quote}}
        rows.append((partner, {'profilePassages': [{'source': source, 'text': quote}], '_sourceMap':mapping,'inputCoverage': coverage}, [], []))
        item = {**recommendation(), 'partnerId': partner['id'], 'partnerName': partner['name'],
                'evidenceType': 'current_capability' if index == 0 else 'unrelated',
                'profileEvidence': [source],
                'evidenceCases': [], 'evidenceDeliverables': []}
        if index == 0 and not keep_current:
            continue
        if index == 1 and scenario == 'unsupported_claim':
            item['evidenceType'] = 'current_capability'
            item['profileEvidence'][0]='unsent-source'
        items.append(item)
    rejected = []
    recs = match._validated_recommendations(items, partners, {p['id']: [] for p in partners}, {p['id']: [] for p in partners}, rejected)
    result = match._validated_outcome(recs, {'recommendations': items, 'supplyStatus': 'sufficient','analysisRefs':[],'_analysis_shape_valid':True}, bool(rejected), rows,
                                      requirement='需要ScopeQuasar能力', catalog_incomplete=scenario == 'incomplete_catalogue')
    assert len(result['recommendations']) == int(keep_current)
    assert result['analysisComplete'] is complete
    assert '本次分析不完整' not in result['answer'] and result['gapAnalysis']==''
    assert '办公合成伙伴' not in result['answer']
    if keep_current:
        assert result['supplyStatus'] == 'sufficient'  # Model coverage stays separate from input diagnostics.
        assert result['recommendations'][0]['recommendationReason']==items[0]['recommendationReason']
