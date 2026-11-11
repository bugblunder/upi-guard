"""Audit the supplied original CSV without assuming previous conversational results."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from sklearn.metrics import roc_auc_score
from .shared import features


def audit(source,out):
    data=pd.read_csv(source)
    rows=data.to_dict('records')
    x=pd.DataFrame(features.feature_rows(rows))
    result=dict(source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        n=len(rows),prevalence=float(data.fraud_label.mean()),
        new_payee_auc=float(roc_auc_score(data.fraud_label,x.new_payee)),
        zero_rate={k:float((x[k]==0).mean()) for k in
                   ['receiver_fanin_24h','payer_incoming_count_1h','pass_through_ratio_1h']})
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('data/synthetic_training.csv'))
    p.add_argument('--out',type=Path,default=Path('research/results/original_data_audit.json'))
    a=p.parse_args();audit(a.source,a.out)
