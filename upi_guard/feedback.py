"""Versioned frozen-feature feedback merged into an explicit training snapshot."""
import csv
import json
from pathlib import Path
from .features import FEATURES, FEATURE_VERSION, parse_time
from .schema import TransactionInput

FIELDS=['transaction_json','features_json','feature_version','fraud_label','label_available_at','source']


def load_snapshot(path):
    result={}
    with open(path,newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        if len(reader.fieldnames or [])!=len(FIELDS) or set(reader.fieldnames or [])!=set(FIELDS):raise ValueError('Expected versioned training/feedback snapshot CSV')
        for item in reader:
            if None in item or any(v is None for v in item.values()):raise ValueError('Malformed feedback CSV row')
            if item['feature_version']!=FEATURE_VERSION:raise ValueError('Feedback feature version mismatch; never recompute frozen history')
            tx=TransactionInput.model_validate(json.loads(item['transaction_json'])).payload()
            features=json.loads(item['features_json'])
            if set(features)!=set(FEATURES):raise ValueError('Feedback feature contract mismatch')
            from math import isfinite
            from .features import NUMERIC
            if any(type(features[k]) not in (int,float) or not isfinite(features[k]) for k in NUMERIC):
                raise ValueError('Feedback numerical features must be finite')
            if any(features[k] != tx[k] for k in ('category', 'channel')):
                raise ValueError('Feedback categorical features must match the immutable transaction')
            if item['fraud_label'] not in ('0','1'):raise ValueError('Feedback requires a confirmed binary label')
            available=parse_time(item['label_available_at'])
            if available.tzinfo is None or available<parse_time(tx['timestamp']):raise ValueError('Label availability must be timezone-aware and no earlier than the event')
            key=tx['transaction_id']
            if key in result:raise ValueError('Duplicate feedback transaction ID')
            result[key]={'tx':tx,'features':features,'label':int(item['fraud_label']),
                         'label_available_at':item['label_available_at'],'source':item['source']}
    return result


def merge_feedback(base_path,feedback_path,output):
    base=load_snapshot(base_path);updates=load_snapshot(feedback_path)
    if not base:raise ValueError('A representative base snapshot is required; feedback-only training is not supported')
    for key,item in updates.items():
        if key in base and (base[key]['tx']!=item['tx'] or base[key]['features']!=item['features']):
            raise ValueError('Conflicting immutable transaction/features in feedback')
        base[key]=item
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    with open(output,'w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for item in sorted(base.values(),key=lambda x:parse_time(x['tx']['timestamp'])):
            writer.writerow(dict(transaction_json=json.dumps(item['tx']),features_json=json.dumps(item['features']),
                feature_version=FEATURE_VERSION,fraud_label=item['label'],label_available_at=item['label_available_at'],source=item['source']))
    return {'rows':len(base),'reviewed_updates':len(updates),'warning':'Selective review labels are biased. Unreviewed payments are never assumed legitimate. Candidate training does not activate a model.'}


def train_snapshot(path,artifacts,seed=42,review_budget=.02):
    from .ml import train
    snapshot=load_snapshot(path)
    rows=[{**v['tx'],'fraud_label':v['label'],'label_available_at':v['label_available_at'],'label_source':v['source']} for v in snapshot.values()]
    return train(rows,artifacts,seed,review_budget=review_budget,
                 frozen={k:v['features'] for k,v in snapshot.items()},data_kind='frozen snapshot; inspect source column for synthetic/reviewed mixture')
