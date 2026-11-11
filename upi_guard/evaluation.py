"""Budget-aware operating points and uncertainty, independent of model fitting."""
import numpy as np
from sklearn.metrics import average_precision_score


def capacity_threshold(p, budget=.02):
    """At most floor(n*budget) validation alerts; ties never exceed the budget."""
    p=np.asarray(p)
    if not 0 < budget <= 1 or not len(p): raise ValueError('Invalid budget or empty scores')
    k=int(len(p)*budget)
    if k==0:return float(np.nextafter(max(p),np.inf))
    ordered=np.sort(p)[::-1]
    if k==len(p):return float(ordered[-1])
    return float(np.nextafter(ordered[k],np.inf))


def prevalence_table(tpr,fpr,prevalences=(.1,.01,.001,.0001)):
    rows=[]
    for rate in prevalences:
        tp=rate*tpr;fp=(1-rate)*fpr
        rows.append({'prevalence':rate,'precision':tp/(tp+fp) if tp+fp else None,
                     'alert_rate':tp+fp,'alerts_per_100000':100000*(tp+fp),
                     'false_alerts_per_100000':100000*fp})
    return rows


def clustered_comparison(y, predictions, payers, seed=42, repetitions=300):
    """Paired payer bootstrap of fixed validation predictions, not refitting CI.

    Reports AP differences. Does not capture time drift, training uncertainty or
    unseen scenarios. Simplicity order is predeclared, not chosen using test F1.
    """
    groups=np.asarray(payers);keys=np.unique(groups);rng=np.random.default_rng(seed)
    indices={k:np.flatnonzero(groups==k) for k in keys}
    point={k:float(average_precision_score(y,p)) for k,p in predictions.items()}
    best=max(point,key=point.get);draws={k:[] for k in predictions}
    for _ in range(repetitions):
        ix=np.concatenate([indices[k] for k in rng.choice(keys,len(keys),replace=True)])
        if len(np.unique(y[ix]))<2:continue
        for k,p in predictions.items():draws[k].append(float(average_precision_score(y[ix],p[ix])))
    comparisons={}
    eligible=[]
    for k in predictions:
        diff=np.array(draws[best])-np.array(draws[k])
        lo,hi=np.quantile(diff,[.025,.975])
        comparisons[k]={'ap':point[k],'ap_interval':list(map(float,np.quantile(draws[k],[.025,.975]))),
                        'best_minus_candidate_interval':[float(lo),float(hi)]}
        if lo<=0:eligible.append(k)
    order=['logistic_regression','random_forest','hist_gradient_boosting']
    selected=next(k for k in order if k in eligible)
    return selected,{'method':'300 paired payer-cluster resamples of fixed validation predictions; 95% percentile intervals',
                     'ap_best':best,'candidates':comparisons,'eligible':eligible,
                     'selection':'Choose simplest candidate whose AP deficit interval includes zero; not proof of equivalence',
                     'limitations':'Selection heuristic; no multiple-comparison correction, refitting uncertainty or temporal drift coverage.'}
