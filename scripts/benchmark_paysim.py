"""Independent PaySim native-schema benchmark; never activates a UPI model."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from upi_guard.ml import metrics, log_odds, probabilities
from upi_guard.evaluation import capacity_threshold, prevalence_table


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',required=True)
    parser.add_argument('--output',default='reports/paysim-benchmark.json');args=parser.parse_args()
    archive=Path(args.archive);h=hashlib.sha256()
    with archive.open('rb') as f:
        while block:=f.read(1024*1024):h.update(block)
    parts=[];offset=0;full_fraud=0;full_n=0
    with zipfile.ZipFile(archive) as z:
        candidates=[n for n in z.namelist() if n.endswith('.csv')]
        if len(candidates)!=1:raise ValueError('Expected one PaySim CSV')
        with z.open(candidates[0]) as f:
            for chunk in pd.read_csv(f,chunksize=250000,usecols=['step','type','amount','oldbalanceOrg','isFraud']):
                ix=(np.arange(len(chunk))+offset)%10==0
                parts.append(chunk.loc[ix]);offset+=len(chunk)
                full_n+=len(chunk);full_fraud+=int(chunk.isFraud.sum())
    frame=pd.concat(parts,ignore_index=True).sort_values('step',kind='stable').reset_index(drop=True)
    frame['log_amount']=np.log1p(frame.amount);frame['log_oldbalance']=np.log1p(frame.oldbalanceOrg)
    features=['log_amount','log_oldbalance','type'];x=frame[features];y=frame.isFraud.to_numpy()
    n=len(frame);cuts=[]
    for frac in (.6,.7,.8):
        c=int(n*frac)
        while c<n and frame.step.iloc[c]==frame.step.iloc[c-1]:c+=1
        cuts.append(c)
    a,b,c=cuts
    splits={'train':slice(0,a),'calibration':slice(a,b),'validation':slice(b,c),'test':slice(c,n)}
    for name,sl in splits.items():
        if len(np.unique(y[sl]))<2:raise ValueError(f'{name} lacks both labels')
    models={};estimators={'logistic_regression':LogisticRegression(class_weight='balanced',max_iter=1000,random_state=42),
        'hist_gradient_boosting':HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,l2_regularization=2,random_state=42)}
    for name,est in estimators.items():
        transform=ColumnTransformer([('numeric',StandardScaler(),features[:2]),('type',OneHotEncoder(sparse_output=False,handle_unknown='ignore'),['type'])])
        pipeline=make_pipeline(transform,est);pipeline.fit(x.iloc[:a],y[:a])
        cal=LogisticRegression().fit(log_odds(pipeline.predict_proba(x.iloc[a:b])[:,1]),y[a:b])
        bundle={'pipeline':pipeline,'calibrator':cal}
        vp=probabilities(bundle,x.iloc[b:c]);tp=probabilities(bundle,x.iloc[c:])
        threshold=capacity_threshold(vp,.02)
        result={'validation':metrics(y[b:c],vp,threshold),'test':metrics(y[c:],tp,threshold)}
        result['prevalence_scenarios']=prevalence_table(result['test']['recall'],result['test']['false_positive_rate'])
        models[name]=result
    report={'source':'https://www.kaggle.com/datasets/ealaxi/paysim1','dataset_version':2,
            'paper':'Lopez-Rojas, Elmir and Axelsson (2016), PaySim: A financial mobile money simulator for fraud detection',
            'archive_sha256':h.hexdigest(),'full_rows':full_n,'full_fraud_count':full_fraud,
            'sampling':'Every tenth row, starting with row zero, irrespective of label; no class resampling',
            'sample_rows':n,'sample_fraud_count':int(y.sum()),'features':features,
            'excluded':'All post-transaction balances, isFlaggedFraud, identifiers and the step feature',
            'splits':{k:{'n':len(frame.iloc[v]),'fraud':int(y[v].sum()),'first_step':int(frame.step.iloc[v].min()),'last_step':int(frame.step.iloc[v].max())} for k,v in splits.items()},
            'models':models,'primary_model':'logistic_regression (predeclared baseline; no selection using test)',
            'limitations':['Independent synthetic generator, not real UPI traffic.','Native-schema benchmark is not validation of the deployed UPI model.',
                'Systematic subsampling can alias row ordering; results apply to this documented sample.',
                'No real-world cost, capacity, intervention effect or calibration claim.']}
    Path(args.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
