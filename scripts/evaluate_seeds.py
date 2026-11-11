"""Frozen active model on new simulator seeds; no tuning or model selection."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from upi_guard.ml import ModelStore, metrics, probabilities
from upi_guard.simulator import generate_transactions
from upi_guard.features import feature_rows, FEATURES
root=Path(__file__).resolve().parents[1];store=ModelStore(root/'artifacts');reports=[]
for seed in (101,202,303):
    rows=generate_transactions(12000,seed);frame=pd.DataFrame(feature_rows(rows))[FEATURES]
    # History is independently simulated; model, calibration and threshold stay frozen.
    x=frame.iloc[9600:];y=np.array([r['fraud_label'] for r in rows[9600:]])
    p=probabilities(store.bundle,x)
    m=metrics(y,p,store.bundle['threshold']);pred=(p>=store.bundle['threshold']) & (x.history_count.to_numpy()>=5)
    reports.append({'seed':seed,'model_metrics':m,'policy_alert_rate':float(pred.mean()),'policy_recall':float(pred[y==1].mean())})
report={'model_version':store.bundle['version'],'seeds':reports,'scope':'Frozen model on three new draws of the same generator. No independent real-world or unseen-scenario validation.'}
(root/'reports'/'seed-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
