"""Research validity checks; run without the web app using unittest discovery."""
from dataclasses import replace
import unittest
import numpy as np
import pandas as pd
from research.typology_sim import SimConfig, generate
from research.shared import features as ft
from research.study import eligible, top_budget, metric, fit_model, psi, interval
from threadpoolctl import threadpool_limits


class ResearchValidity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=SimConfig(episodes_per_week=60,seed=7)
        cls.rows=generate(cls.config)
        cls.frame=pd.DataFrame(ft.feature_rows(cls.rows))

    def test_seed_determinism(self):
        self.assertEqual(self.rows,generate(self.config))
        self.assertNotEqual(self.rows,generate(replace(self.config,seed=8)))

    def test_pairing_and_labels(self):
        control=generate(self.config,control=True)
        pre=self.config.drift_week*self.config.episodes_per_week*3
        self.assertEqual(self.rows[:pre],control[:pre])
        for field in ['timestamp','transaction_id','fraud_label','observed_label']:
            self.assertEqual([r[field] for r in self.rows],[r[field] for r in control])
        self.assertNotEqual(self.rows[pre:],control[pre:])

    def test_contract_and_chronology(self):
        self.assertEqual(list(self.frame.columns),ft.FEATURES)
        for r in self.rows:
            self.assertGreater(float(r['amount']),0)
            self.assertLessEqual(float(r['amount']),1e6)
            self.assertIn(r['category'],['transfer','shopping'])
            self.assertIn(r['channel'],['push','collect','qr'])
        self.assertEqual([r['timestamp'] for r in self.rows],sorted(r['timestamp'] for r in self.rows))
        self.assertEqual(len(self.rows),len({r['transaction_id'] for r in self.rows}))
        from datetime import datetime
        start=datetime.fromisoformat(self.rows[0]['timestamp'])
        for row in self.rows:
            actual=(datetime.fromisoformat(row['timestamp'])-start).total_seconds()/604800+self.rows[0]['event_week']
            self.assertAlmostEqual(actual,row['event_week'],places=8)

    def test_future_and_label_invariance(self):
        short=self.rows[:200]
        self.assertEqual(ft.feature_rows(short),self.frame.iloc[:200].to_dict('records'))
        flipped=[{**r,'fraud_label':1-r['fraud_label'],'observed_label':1-r['observed_label'],
                  'scenario':'arbitrary','week':999} for r in short]
        self.assertEqual(ft.feature_rows(short),ft.feature_rows(flipped))

    def test_graph_signals_and_confounds(self):
        from research.study import GRAPH
        for column in GRAPH:
            self.assertGreater((self.frame[column]>0).sum(),0)
        legitimate=np.array([r['scenario']=='merchant' for r in self.rows])
        self.assertGreater((self.frame.loc[legitimate,'payer_incoming_count_1h']>0).sum(),0)
        self.assertGreater((self.frame.loc[legitimate,'receiver_fanin_24h']>0).sum(),0)

    def test_maturity_cutoff(self):
        event=np.array([3.,5.,6.9,7.,7.1,8.9,10.])
        allowed=eligible(event,10,3,4)
        np.testing.assert_array_equal(allowed,[False,True,True,False,False,False,False])
        self.assertTrue(np.all(event[allowed]+3<10))
        np.testing.assert_array_equal(eligible(event,10,0,4),[False,False,True,True,True,True,False])

    def test_review_capacity_ties_and_values(self):
        chosen=top_budget(np.ones(101),.05)
        self.assertEqual(chosen.sum(),5)
        np.testing.assert_array_equal(np.where(chosen)[0],np.arange(5))
        y=np.array([1,0,1,0]);score=np.array([.9,.8,.2,.1])
        m=metric(y,score,np.array([10,1,30,1]),.5,np.array(['mule']*4))
        self.assertEqual(m['recall'],.5)
        self.assertEqual(m['value_recall'],.25)

    def test_no_positive_metrics_are_missing(self):
        m=metric(np.zeros(10),np.ones(10)*.1,np.ones(10),.1,np.array(['legitimate']*10))
        self.assertIsNone(m['recall']);self.assertIsNone(m['average_precision'])

    def test_model_drops_metadata_and_ablation_features(self):
        x=self.frame.iloc[:800]
        y=np.array([r['observed_label'] for r in self.rows[:800]])
        with threadpool_limits(limits=1):
            model=fit_model(x,y,'hgb',7,['new_payee','new_device'])
            expected=model.predict_proba(x.iloc[:10])
            changed=x.iloc[:10].copy();changed['new_payee']=123;changed['new_device']=456
            np.testing.assert_array_equal(expected,model.predict_proba(changed))
        names=model[0].get_feature_names_out()
        self.assertFalse(any('new_payee' in k or 'new_device' in k for k in names))

    def test_statistics(self):
        self.assertEqual(psi(np.arange(100),np.arange(100)),0.)
        self.assertEqual(interval([1.])['ci95_low'],None)
        self.assertAlmostEqual(interval([1.,2.,3.])['mean'],2.)


if __name__=='__main__':unittest.main()
