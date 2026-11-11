"""Exploratory alarm/performance association, including stationary false alarms."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .study import interval


def analyze(folder):
    protocol=json.loads((folder/'protocol.json').read_text())
    start=protocol['simulator']['drift_week']
    data=pd.read_csv(folder/'monitoring.csv')
    records=[]
    for (seed,arm,model),group in data.groupby(['seed','arm','model']):
        group=group.sort_values('week')
        baseline=group.loc[group.week<start,'static_recall'].mean()
        after=group[group.week>=start].copy()
        # This label-dependent definition is retrospective, never a monitor input.
        harm=after.static_recall < .8*baseline
        for monitor in ['feature_alarm','score_alarm','alert_rate_alarm']:
            fired=after[monitor].astype(bool)
            first_harm=int(after.loc[harm,'week'].min()) if harm.any() else None
            first_alarm=int(after.loc[fired,'week'].min()) if fired.any() else None
            records.append(dict(seed=int(seed),arm=arm,model=model,monitor=monitor,
                baseline_recall=baseline,post_alarm_rate=float(fired.mean()),
                pre_alarm_rate=float(group.loc[group.week<start,monitor].mean()),
                harmful_weeks=int(harm.sum()),silently_harmful_weeks=int((harm & ~fired).sum()),
                harmful_week_coverage=float(fired[harm].mean()) if harm.any() else None,
                first_harm_week=first_harm,first_alarm_week=first_alarm,
                alarm_minus_harm_weeks=first_alarm-first_harm if first_harm is not None and first_alarm is not None else None))
    frame=pd.DataFrame(records)
    frame.to_csv(folder/'monitor_per_seed.csv',index=False)
    summary=[]
    for (arm,model,monitor),group in frame.groupby(['arm','model','monitor']):
        for metric in ['post_alarm_rate','pre_alarm_rate','harmful_week_coverage']:
            values=group[metric].dropna().values
            if len(values):summary.append(dict(arm=arm,model=model,monitor=monitor,metric=metric,**interval(values)))
    pd.DataFrame(summary).to_csv(folder/'monitor_summary.csv',index=False)
    print('Saved exploratory monitor association tables:',folder)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path,nargs='?',default=Path('research/results'))
    analyze(p.parse_args().folder)
