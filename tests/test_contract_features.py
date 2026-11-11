from datetime import date
import pytest
from pydantic import ValidationError
from upi_guard.schema import TransactionInput,calendar_age
from upi_guard.features import build_features,feature_rows,FEATURES
from upi_guard.simulator import generate_transactions


@pytest.mark.parametrize('field,value',[
    ('amount','-1'),('amount','0'),('amount','1.001'),('amount','NaN'),('amount','Infinity'),
    ('amount','1000001'),('timestamp','2025-01-01T12:00:00'),('timestamp','2100-01-01T12:00:00Z'),
    ('timestamp','not-a-date'),('account_age_days',-1),('failed_attempts_1h',-1),
    ('payer_id','bad<script>'),('channel','unknown'),('category','unknown')])
def test_invalid_contract(payload,field,value):
    payload[field]=value
    with pytest.raises(ValidationError):TransactionInput.model_validate(payload)


def test_forbid_labels_in_scoring(payload):
    payload['fraud_label']=1
    with pytest.raises(ValidationError):TransactionInput.model_validate(payload)


def test_offset_normalization(payload):
    payload['timestamp']='2025-01-01T17:30:00+05:30'
    assert TransactionInput.model_validate(payload).timestamp.hour==12


def test_calendar_age():
    assert calendar_age(date(2000,10,10),date(2025,10,9))==24
    assert calendar_age(date(2000,10,10),date(2025,10,10))==25
    with pytest.raises(ValueError):calendar_age(date(2030,1,1),date(2025,1,1))


def test_no_future_equal_time_or_other_user_leakage(payload):
    old={**payload,'timestamp':'2025-01-01T11:58:00Z','amount':'100.00'}
    future={**payload,'timestamp':'2025-01-01T12:01:00Z','amount':'99999.00'}
    foreign={**old,'payer_id':'another-payer'}
    f=build_features(payload,[old,future,payload,foreign])
    assert f['count_5m']==1 and f['history_count']==1 and f['amount_ratio']==5
    assert f['new_payee']==0 and f['new_device']==0
    assert 'fraud_label' not in f and 'payer_id' not in f and 'trans_year' not in f


def test_history_window_expiration(payload):
    old={**payload,'timestamp':'2024-11-01T11:00:00Z'}
    assert build_features(payload,[old])['history_count']==0


def test_simulator_reproducible_and_valid():
    a=generate_transactions(250,7);b=generate_transactions(250,7)
    assert a==b and len({r['payer_id'] for r in a})<len(a)
    assert a==sorted(a,key=lambda r:(r['timestamp'],r['transaction_id']))
    for row in a:TransactionInput.model_validate({k:v for k,v in row.items() if k not in ('fraud_label','scenario')})
    features=feature_rows(a)
    assert set(features[-1])==set(FEATURES)


def test_offline_features_ignore_labels():
    rows=generate_transactions(100,3)
    changed=[{**r,'fraud_label':1-r['fraud_label'],'scenario':'anything'} for r in rows]
    assert feature_rows(rows)==feature_rows(changed)
