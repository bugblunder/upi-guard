# Data card — revision 2.1

The supplied 12,000-row dataset comes from `upi_guard/simulator.py`, seed 42. It is **synthetic**, with an intentionally high fraud rate and repeated scenario rules. The model can learn the generator. High global importance of `new_payee` is evidence of model reliance on this shortcut, not evidence that new UPI recipients are fraudulent. Changing the threshold or adding algorithms cannot repair that provenance problem.

The simulator includes ordinary payments, unusual legitimate payments, bursts, takeover and social-engineering scenarios. Its labels are probabilistic scenario outputs, not observed customer outcomes. The same scenario families occur across temporal partitions. It has no validated population of mule accounts. Its incoming-payment graph features are largely inactive; their implementation is tested using constructed cases, without claiming fraud-detection effectiveness.

## Transaction contract

Required: `transaction_id`, `timestamp`, `payer_id`, `payee_id`, `device_id`, `amount`, `category`, `channel`. Identifiers are 3–64 letters, digits, hyphens or underscores. Amount is positive, at most INR 1,000,000, with at most two decimal places. Category: transfer/grocery/shopping/bills/travel/food/other. Channel: push/qr/collect. Timestamps require an offset, normalize to UTC and allow up to five minutes ahead of server time. Dates before 2020 are rejected.

`account_age_days` and `failed_attempts_1h` are optional deprecated compatibility fields. They are validated and stored with the original request but **never enter model features, rules or decisions**. A future trusted provider integration would need authoritative, timestamped sources before these features could be restored.

Scoring accepts no label. Training CSV adds `fraud_label` (0/1) and optional `scenario`. No raw identifier, outcome or absolute year enters the supervised feature matrix.

## Frozen features

Feature contract `2.1.0` contains amount, payer velocity, 30-day amount ratio and payer history, observed-history duration, device/payee novelty, cyclic time, category/channel, 24-hour recipient fan-in, payer incoming count and recent incoming-funds ratio. These are simple local graph aggregates, not a graph neural network or confirmed mule classifier. Observed-history duration is not account age. A recipient's incoming transfers and sender transfers are queried from the stored payment ledger.

Online history includes only committed rows available to the current scoring query, strictly earlier in event time and within 30 days. Equal-time events are excluded. Concurrent transactions can have different availability histories. Late arrivals are accepted and marked; previous snapshots remain immutable. Offline chronological simulation assumes chronological arrival. For actual feedback training, use the frozen feature export; recomputing all historical features would leak late-arriving information.

A small future clock skew is preserved and recorded. It is not silently converted to server time. An upstream trusted payment feed and a clear event-time contract are still required for actual financial integration.

## Public comparison

`reports/paysim-benchmark.json` records a separate benchmark using the author's PaySim dataset, version 2: https://www.kaggle.com/datasets/ealaxi/paysim1 . The project repository is https://github.com/EdgarLopezPhD/PaySim . Cite Lopez-Rojas, Elmir and Axelsson, “PaySim: A financial mobile money simulator for fraud detection”, EMSS 2016.

Kaggle metadata retrieved for this run identifies the dataset license as CC BY-SA 4.0. The dataset archive is not redistributed in this ZIP. Download it from its source and run `python scripts/benchmark_paysim.py --archive /path/to/paysim.zip`. Its SHA-256, sampling and partition boundaries are in the report. The simulator source has a separate GPL license; no simulator source was copied into this project.

The benchmark reads all 6,362,620 rows and retains every tenth row irrespective of label: 636,262 events. It uses log amount, log pre-transaction origin balance and payment type. Post-transaction balances, existing fraud flags, identifiers and the time-step feature are excluded. Entire hourly steps stay within one partition. The native schema is evaluated separately, without inventing UPI device or channel attributes. PaySim is an independent **synthetic** source, not actual UPI validation. IEEE-CIS was not evaluated.

## Reviewed outcomes

The versioned feedback CSV stores transaction JSON, original features JSON, feature version, confirmed label, label-availability timestamp and source. It excludes incompatible legacy feature snapshots and reports their count in `X-Skipped-Legacy-Rows`. Unreviewed transactions are never assigned a legitimate label. Reviewed cases are selection-biased; representative delayed outcomes or an audited sampling program remain necessary.
