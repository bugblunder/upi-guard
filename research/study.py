"""Paired stationary/drift experiments, chronological replay and mature labels."""
import argparse
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
import pandas as pd
import scipy
from scipy.stats import t
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits
from .shared import features as ft, monitoring
from .typology_sim import SimConfig, generate, configuration

GRAPH = ['receiver_fanin_24h', 'payer_incoming_count_1h', 'pass_through_ratio_1h']
STRATEGIES = ['static', 'weekly_delay0', 'weekly_delay1', 'weekly_delay3',
              'cumulative_delay1', 'static_no_graph', 'static_no_novelty']


def eligible(event_week, current_week, delay, window=4):
    """Labels arrive event_week+delay; strict earlier-than scoring cutoff."""
    event_week = np.asarray(event_week)
    mature = event_week + delay < current_week
    return mature & (event_week >= 5) & (event_week >= current_week-delay-window if window else True)


def fit_model(frame, labels, model, seed, drop=()):
    numeric = [x for x in ft.NUMERIC if x not in drop]
    pre = ColumnTransformer([('numeric', StandardScaler(), numeric),
        ('category', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ft.CATEGORICAL)])
    estimator = (HistGradientBoostingClassifier(max_iter=70, max_leaf_nodes=10, min_samples_leaf=25,
                     l2_regularization=2, early_stopping=False, random_state=seed)
                 if model == 'hgb' else LogisticRegression(max_iter=1200, C=.2, random_state=seed))
    pipeline = make_pipeline(pre, estimator)
    if len(np.unique(labels)) != 2:
        raise ValueError('Training requires both classes; increase sample size')
    pipeline.fit(frame, labels)
    return pipeline


def top_budget(scores, budget):
    """Exact floor(n*budget) selection; ties broken by chronological row order."""
    scores = np.asarray(scores)
    if not 0 < budget <= 1:
        raise ValueError('budget must be in (0,1]')
    k = math.floor(len(scores)*budget)
    chosen = np.zeros(len(scores), dtype=bool)
    if k:
        chosen[np.argsort(-scores, kind='stable')[:k]] = True
    return chosen


def metric(y, scores, amounts, budget, groups):
    chosen = top_budget(scores, budget)
    total = int(y.sum())
    caught = int(y[chosen].sum())
    value = float(np.sum(amounts*y))
    out = dict(n=len(y), fraud_count=total, prevalence=float(y.mean()),
               alert_count=int(chosen.sum()), recall=caught/total if total else None,
               precision=caught/int(chosen.sum()) if chosen.any() else None,
               average_precision=float(average_precision_score(y, scores)) if total and total<len(y) else None,
               roc_auc=float(roc_auc_score(y, scores)) if total and total<len(y) else None,
               brier=float(brier_score_loss(y, scores)),
               value_recall=float(np.sum(amounts*y*chosen))/value if value else None)
    for family in ('mule', 'takeover'):
        mask = (groups == family) & (y == 1)
        out[f'{family}_recall'] = float(chosen[mask].mean()) if mask.any() else None
    return out


def psi(reference, current):
    edges = np.unique(np.r_[-np.inf, np.quantile(reference, np.linspace(0, 1, 11)), np.inf])
    a = np.histogram(reference, edges)[0]+.5
    b = np.histogram(current, edges)[0]+.5
    a, b = a/a.sum(), b/b.sum()
    return float(np.sum((b-a)*np.log(b/a)))


def run_arm(config, control, models, budget):
    rows = generate(config, control)
    x = pd.DataFrame(ft.feature_rows(rows))[ft.FEATURES]
    weeks = np.array([r['week'] for r in rows])
    event = np.array([r['event_week'] for r in rows])
    y = np.array([r['fraud_label'] for r in rows])
    observed = np.array([r['observed_label'] for r in rows])
    amounts = np.array([float(r['amount']) for r in rows])
    groups = np.array([r['scenario'] for r in rows])
    train = (weeks >= 5) & (weeks < 9)
    reference = (weeks >= 9) & (weeks < 12)
    profile = monitoring.reference_profile(x[reference])
    results, alarms = [], []
    source_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    diagnostic = dict(seed=config.seed, arm='control' if control else 'drift', n=len(rows),
        data_sha256=source_hash, prevalence=float(y.mean()),
        graph_nonzero={k:float((x[k]>0).mean()) for k in GRAPH},
        novelty_auc={k:float(roc_auc_score(y, x[k])) for k in ('new_payee','new_device')})
    for model in models:
        static = fit_model(x[train], observed[train], model, config.seed)
        no_graph = fit_model(x[train], observed[train], model, config.seed, GRAPH)
        no_novelty = fit_model(x[train], observed[train], model, config.seed, ['new_payee','new_device'])
        ref_score = static.predict_proba(x[reference])[:,1]
        threshold = float(np.quantile(ref_score, 1-budget))
        baseline_rate = float((ref_score >= threshold).mean())
        for week in range(12, config.weeks):
            test = weeks == week
            fixed_score = static.predict_proba(x[test])[:,1]
            scores_by_strategy = {'static':fixed_score,
                'static_no_graph':no_graph.predict_proba(x[test])[:,1],
                'static_no_novelty':no_novelty.predict_proba(x[test])[:,1]}
            for name, delay, window in [('weekly_delay0',0,4),('weekly_delay1',1,4),
                                       ('weekly_delay3',3,4),('cumulative_delay1',1,None)]:
                allowed = eligible(event, week, delay, window)
                fresh = fit_model(x[allowed], observed[allowed], model, config.seed)
                scores_by_strategy[name] = fresh.predict_proba(x[test])[:,1]
            for name, scores in scores_by_strategy.items():
                results.append(dict(seed=config.seed, arm=diagnostic['arm'], model=model, week=week,
                    strategy=name, phase='pre' if week<config.drift_week else 'mix' if week<config.adaptation_week else 'adapted',
                    **metric(y[test], scores, amounts[test], budget, groups[test])))
            diag = monitoring.drift_summary(x[test].to_dict('records'), profile)
            score_psi = psi(ref_score, fixed_score)
            rate = float((fixed_score >= threshold).mean())
            alarms.append(dict(seed=config.seed, arm=diagnostic['arm'], model=model, week=week,
                feature_alarm=diag['status']=='review',
                max_feature_psi=max((a.get('psi',0) for a in diag['features']),default=0),
                score_psi=score_psi, score_alarm=score_psi>.2,
                fixed_alert_rate=rate, alert_rate_alarm=abs(rate-baseline_rate)>.03,
                static_recall=results[-len(scores_by_strategy)]['recall']))
    return results, alarms, diagnostic


def interval(values):
    values = np.asarray(values, dtype=float)
    n = len(values)
    mean = float(values.mean())
    half = float(t.ppf(.975,n-1)*values.std(ddof=1)/np.sqrt(n)) if n>1 else None
    return dict(n_seeds=n, mean=mean, ci95_low=mean-half if half is not None else None,
                ci95_high=mean+half if half is not None else None)


def summarize(frame, output):
    # Weeks are correlated; aggregate within seed BEFORE computing uncertainty.
    metrics = ['recall','precision','average_precision','value_recall','mule_recall','brier']
    means = frame.groupby(['seed','arm','model','strategy','phase'])[metrics].mean().reset_index()
    summary = []
    for key, group in means.groupby(['arm','model','strategy','phase']):
        for name in metrics:
            values = group[name].dropna().values
            if len(values):
                summary.append(dict(zip(['arm','model','strategy','phase'],key),metric=name,**interval(values)))
    pd.DataFrame(summary).to_csv(output/'summary.csv',index=False)
    comparisons = []
    for (model,strategy), group in means.groupby(['model','strategy']):
        for name in ['recall','average_precision']:
            pivot = group.pivot(index='seed', columns=['arm','phase'], values=name)
            keys = [('drift','adapted'),('drift','pre'),('control','adapted'),('control','pre')]
            if all(k in pivot.columns for k in keys):
                delta = pivot[keys[0]]-pivot[keys[1]]-pivot[keys[2]]+pivot[keys[3]]
                comparisons.append(dict(model=model,strategy=strategy,metric=name,**interval(delta.dropna())))
    pd.DataFrame(comparisons).to_csv(output/'paired_control.csv',index=False)
    comparisons=[]
    for model, group in means[(means.arm=='drift') & (means.phase=='adapted')].groupby('model'):
        for name in ['recall','average_precision','mule_recall']:
            pivot=group.pivot(index='seed', columns='strategy',values=name)
            for strategy in STRATEGIES[1:]:
                delta=(pivot[strategy]-pivot['static']).dropna()
                if len(delta):comparisons.append(dict(model=model,strategy_minus_static=strategy,metric=name,**interval(delta)))
    pd.DataFrame(comparisons).to_csv(output/'paired_strategies.csv',index=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds',type=int,default=5)
    p.add_argument('--seed-start',type=int,default=0)
    p.add_argument('--episodes',type=int,default=240)
    p.add_argument('--models',nargs='+',choices=['hgb','lr'],default=['hgb','lr'])
    p.add_argument('--arms',nargs='+',choices=['drift','control'],default=['drift','control'])
    p.add_argument('--budget',type=float,default=.05)
    p.add_argument('--fraud-rate',type=float,default=.04)
    p.add_argument('--adaptation-strength',type=float,default=.8)
    p.add_argument('--label-noise',type=float,default=.005)
    p.add_argument('--out',type=Path,default=Path('research/results'))
    args=p.parse_args()
    if args.seeds<1 or args.seed_start<0 or not 0<args.budget<1: p.error('Invalid seeds, seed-start or budget')
    config=SimConfig(episodes_per_week=args.episodes,fraud_episode_rate=args.fraud_rate,
                     adaptation_strength=args.adaptation_strength,label_flip_rate=args.label_noise)
    args.out.mkdir(parents=True,exist_ok=False)
    sources={str(f.relative_to(Path.cwd())):hashlib.sha256(f.read_bytes()).hexdigest()
             for f in sorted((Path.cwd()/'research').glob('*.py'))}
    for name in ['features','monitoring']:
        f=Path.cwd()/'upi_guard'/f'{name}.py'
        sources[str(f.relative_to(Path.cwd()))]=hashlib.sha256(f.read_bytes()).hexdigest()
    protocol=dict(simulator=configuration(config),seeds=list(range(args.seed_start,args.seed_start+args.seeds)),
        models=args.models,arms=args.arms,budget=args.budget,python=platform.python_version(),
        numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,sklearn=sklearn.__version__,
        command=sys.argv,source_sha256=sources,
        partitions={'warmup':'weeks 0-4','initial_train':'weeks 5-8','monitor_reference':'weeks 9-11','evaluation':f'weeks 12-{config.weeks-1}'},
        uncertainty='95% t intervals over per-seed means or paired differences; not real-world uncertainty.')
    (args.out/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    results,alarms,diagnostics=[],[],[]
    with threadpool_limits(limits=1):
        for seed in protocol['seeds']:
            for arm in args.arms:
                print(f'seed={seed} arm={arm}',flush=True)
                r,a,d=run_arm(replace(config,seed=seed),arm=='control',args.models,args.budget)
                results.extend(r);alarms.extend(a);diagnostics.append(d)
                frame=pd.DataFrame(results)
                frame.to_csv(args.out/'weekly_metrics.csv',index=False)
                pd.DataFrame(alarms).to_csv(args.out/'monitoring.csv',index=False)
                (args.out/'diagnostics.json').write_text(json.dumps(diagnostics,indent=2),encoding='utf-8')
                summarize(frame,args.out)
    print(f'Completed: {args.out}',flush=True)


if __name__=='__main__':main()
