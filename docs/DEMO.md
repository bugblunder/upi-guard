# Demonstration — revision 2.1

1. Install using README, initialize an administrator and load 300 demo events. Explain that every payment and fraud label is synthetic. A small cold-start demo may have no automatic cases.
2. Open Transactions, search an ID, and click **Open case**. Explain that an analyst may investigate an unflagged payment. Show frozen observed features and separately labelled SHAP contributions, including their units and reconstruction check.
3. Claim the case, add notes and confirm a demonstration outcome. Reopen it to show audit history and optimistic revisions. Do not pretend this outcome came from a real bank.
4. Show the Model page. At the 2% validation budget, inspected synthetic test recall is only 11.81%; the old high-recall policy overloaded the review queue. Show prevalence sensitivity and alternative budgets. Unseen-payer recall is zero at the chosen threshold. Neither policy is production-ready.
5. Submit the same ID twice: the second result is a replay. Change its amount: 409. Submit an older event under a new ID: accepted with a late-arrival marker. Small future clock skew is tolerated. Old assessments remain unchanged.
6. Export feedback as admin. Explain `merge-feedback` and `train-snapshot`: original features and label availability are preserved, unreviewed events are not labelled legitimate, training produces a candidate without activation.
7. Show `reports/paysim-benchmark.json`: independent synthetic benchmark in a different schema, not deployed-UPI validation. Show the public-data base-rate problem and the small validation fraud count.
8. Show `reports/load-contention.json`: 2,000 requests, no unexpected responses, but poor tail latency. SQLite demo performance is not bank throughput.

For a viva, the defensible contribution is a reproducible risk-investigation engineering prototype with explicit evidence limits. Do not claim a novel fraud algorithm, real UPI accuracy, operationally validated thresholds, solved mule detection, or an industrial production deployment.
