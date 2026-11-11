import json
import shutil
from pathlib import Path
import numpy as np
from upi_guard.ml import ModelStore,drift_summary,threshold_for,train
from upi_guard.features import build_features
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_artifact_reload_prediction_identical(payload):
    a=ModelStore(ROOT/'artifacts');b=ModelStore(ROOT/'artifacts')
    assert a.bundle is not None and a.score(build_features(payload,[]))==b.score(build_features(payload,[]))


def test_model_checksum_fail_closed(tmp_path):
    shutil.copytree(ROOT/'artifacts',tmp_path/'artifacts')
    root=tmp_path/'artifacts';version=json.loads((root/'active.json').read_text())['version']
    with open(root/version/'model.joblib','ab') as f:f.write(b'changed')
    assert ModelStore(root).bundle is None


def test_artifact_path_traversal_rejected(tmp_path):
    (tmp_path/'active.json').write_text(json.dumps({'version':'../outside'}))
    assert ModelStore(tmp_path).bundle is None


def test_drift_detects_large_shift():
    d=drift_summary([{'x':10}]*40,{'x':{'mean':0,'std':1}})
    assert d['status']=='review' and d['features'][0]['flag']


def test_cost_threshold_catches_expensive_miss():
    y=np.array([0,0,1]);p=np.array([.1,.2,.15])
    threshold=threshold_for(y,p,fn_cost=25,fp_cost=1)
    assert threshold<=.15


def test_training_rejects_insufficient_data(tmp_path):
    with pytest.raises(ValueError):train([],tmp_path)
