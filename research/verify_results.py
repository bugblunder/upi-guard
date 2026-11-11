"""Reject incomplete, mismatched or inconsistent main-study result artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd


def verify(folder):
    p=json.loads((folder/'protocol.json').read_text())
    w=pd.read_csv(folder/'weekly_metrics.csv')
    m=pd.read_csv(folder/'monitoring.csv')
    diagnostics=json.loads((folder/'diagnostics.json').read_text())
    weeks=list(range(12,p['simulator']['weeks']))
    strategies=['static','static_no_graph','static_no_novelty','weekly_delay0','weekly_delay1','weekly_delay3','cumulative_delay1']
    expected={(seed,arm,model,strategy,week) for seed in p['seeds'] for arm in p['arms']
              for model in p['models'] for strategy in strategies for week in weeks}
    actual=list(w[['seed','arm','model','strategy','week']].itertuples(index=False,name=None))
    assert len(actual)==len(set(actual)) and set(actual)==expected,'Missing/duplicate weekly metrics'
    expected_monitors={(s,a,model,week) for s in p['seeds'] for a in p['arms'] for model in p['models'] for week in weeks}
    actual_monitors=list(m[['seed','arm','model','week']].itertuples(index=False,name=None))
    assert len(actual_monitors)==len(set(actual_monitors)) and set(actual_monitors)==expected_monitors,'Incomplete monitor rows'
    for relative,digest in p['source_sha256'].items():
        assert hashlib.sha256(Path(relative).read_bytes()).hexdigest()==digest,f'Source changed: {relative}'
    assert len(diagnostics)==len(p['seeds'])*len(p['arms'])
    n=p['simulator']['weeks']*p['simulator']['episodes_per_week']*3
    assert all(d['n']==n for d in diagnostics)
    assert (w.alert_count==(w.n*p['budget']).astype(int)).all(),'Budget exceeded or underspent'
    assert (w.fraud_count>0).all(),'Report explicitly supports only main run with positive weeks'
    if set(p['arms'])=={'drift','control'}:
        paired=w.pivot(index=['seed','model','strategy','week'],columns='arm',values='fraud_count')
        assert paired.control.equals(paired.drift),'Arm outcomes differ'
        for model in p['models']:
            d=w[(w.model==model)&(w.week<p['simulator']['drift_week'])]
            pair=d.pivot(index=['seed','strategy','week'],columns='arm',values='recall')
            assert pair.control.equals(pair.drift),'Pre-intervention arms differ'
    result=dict(status='complete',seeds=p['seeds'],models=p['models'],arms=p['arms'],
                weekly_rows=len(w),monitor_rows=len(m),events_per_seed_arm=n,
                total_simulated_events=n*len(diagnostics),source_hashes_verified=True)
    (folder/'completion.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path,nargs='?',default=Path('research/results'))
    verify(p.parse_args().folder)
