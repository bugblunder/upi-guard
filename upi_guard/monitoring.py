"""Distribution diagnostics; thresholds are illustrative and require tuning."""
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from scipy.spatial.distance import jensenshannon
from .features import NUMERIC, CATEGORICAL


def reference_profile(frame):
    reference={}
    for k in NUMERIC:
        x=frame[k].to_numpy(dtype=float)
        edges=np.unique(np.quantile(x,np.linspace(0,1,11)))
        # Retain constant-feature value as a boundary so novel values are visible.
        edges=np.unique(np.r_[-np.inf,edges,np.inf])
        counts,_=np.histogram(x,bins=edges)
        reference[k]={'kind':'numeric','mean':float(np.mean(x)),'std':float(np.std(x)),
                      'min':float(min(x)),'max':float(max(x)),
                      'edges':[None if not np.isfinite(v) else float(v) for v in edges],
                      'counts':counts.tolist(),'sample':x[np.linspace(0,len(x)-1,min(500,len(x)),dtype=int)].tolist()}
    for k in CATEGORICAL:
        reference[k]={'kind':'categorical','counts':frame[k].value_counts().to_dict()}
    return reference


def drift_summary(rows, reference):
    if len(rows)<30:return {'status':'insufficient_data','sample_size':len(rows),'features':[]}
    frame=pd.DataFrame(rows);items=[]
    for k,r in reference.items():
        if k not in frame:continue
        if r.get('kind')=='categorical':
            counts=frame[k].value_counts().to_dict();keys=sorted(set(counts)|set(r['counts']))
            p=np.array([r['counts'].get(v,0)+.5 for v in keys]);q=np.array([counts.get(v,0)+.5 for v in keys])
            js=float(jensenshannon(p/p.sum(),q/q.sum(),base=2)**2)
            unseen=sum(n for v,n in counts.items() if v not in r['counts'])/len(rows)
            items.append({'feature':k,'js_divergence':js,'unseen_rate':unseen,'flag':js>.1 or unseen>.05})
        else:
            x=frame[k].to_numpy(dtype=float);shift=abs(float(np.mean(x))-r['mean'])/max(r['std'],.1)
            item={'feature':k,'standardized_mean_shift':round(shift,3),'flag':shift>1}
            if 'edges' in r:
                edges=np.array([-np.inf if i==0 else np.inf if i==len(r['edges'])-1 else v for i,v in enumerate(r['edges'])])
                counts,_=np.histogram(x,bins=edges);p=np.array(r['counts'],dtype=float)+.5;q=counts+.5
                p/=p.sum();q/=q.sum();psi=float(np.sum((q-p)*np.log(q/p)))
                ks=ks_2samp(r['sample'],x)
                item.update(psi=psi,ks_statistic=float(ks.statistic),ks_pvalue=float(ks.pvalue))
                # Effect-size plus corrected p-value; dependence still limits inference.
                item['flag']=bool(psi>.2 or (ks.statistic>.15 and ks.pvalue<.01/max(len(reference),1)))
            items.append(item)
    return {'status':'review' if any(i['flag'] for i in items) else 'stable','sample_size':len(rows),'features':items,
            'note':'PSI/KS and categorical JS/OOV are diagnostics, not proof of performance degradation. Correlated events and small samples limit inference.'}
