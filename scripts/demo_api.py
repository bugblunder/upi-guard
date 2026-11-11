"""A runnable CSRF-protected scoring example using a user-supplied password."""
import getpass
import uuid
from datetime import datetime,timezone
import requests
base='http://127.0.0.1:5000'
s=requests.Session()
token=s.get(base+'/api/csrf').json()['csrf_token']
r=s.post(base+'/api/login',json={'username':input('Username: '),'password':getpass.getpass('Password: ')},headers={'X-CSRF-Token':token});r.raise_for_status()
token=r.json()['csrf_token']
payload={'transaction_id':'api-'+uuid.uuid4().hex[:16],'timestamp':datetime.now(timezone.utc).isoformat(),
 'payer_id':'api-demo-payer','payee_id':'api-demo-payee','device_id':'api-demo-device','amount':'499.00',
 'category':'shopping','channel':'qr','account_age_days':200,'failed_attempts_1h':0}
r=s.post(base+'/api/transactions',json=payload,headers={'X-CSRF-Token':token});r.raise_for_status();print(r.json())
# Exact replay must return 200 with replayed=true and the same original score.
r=s.post(base+'/api/transactions',json=payload,headers={'X-CSRF-Token':token});r.raise_for_status();print(r.json())
