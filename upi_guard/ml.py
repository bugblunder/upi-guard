"""Temporal model selection, calibration, threshold tuning and trusted artifacts."""
import hashlib
import io
import json
import os
import platform
from pathlib import Path
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
    average_precision_score, roc_auc_score, confusion_matrix, brier_score_loss,
    precision_recall_curve, roc_curve)
from sklearn.inspection import permutation_importance
from .evaluation import capacity_threshold, clustered_comparison, prevalence_table
from .features import NUMERIC, CATEGORICAL, FEATURES, FEATURE_VERSION, feature_rows


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temp, path)


def log_odds(scores):
    scores = np.clip(scores, 1e-6, 1-1e-6)
    return np.log(scores/(1-scores)).reshape(-1, 1)


def probabilities(bundle, frame):
    raw = bundle["pipeline"].predict_proba(frame)[:, 1]
    return bundle["calibrator"].predict_proba(log_odds(raw))[:, 1]


def metrics(y, p, threshold):
    pred = p >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    both = len(np.unique(y)) == 2
    return {"n": len(y), "fraud_count": int(sum(y)), "fraud_rate": float(np.mean(y)),
            "accuracy": float(accuracy_score(y, pred)),
            "precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "f1": float(f1_score(y, pred, zero_division=0)),
            "false_positive_rate": float(fp/max(tn+fp, 1)),
            "average_precision": float(average_precision_score(y, p)) if both else None,
            "roc_auc": float(roc_auc_score(y, p)) if both else None,
            "brier_score": float(brier_score_loss(y, p)),
            "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
            "alert_rate": float(np.mean(pred)), "threshold": float(threshold)}


def threshold_for(y, p, fn_cost=25, fp_cost=1):
    grid = np.unique(np.r_[np.linspace(.01, .99, 99), p])
    return float(min(grid, key=lambda t: (fn_cost*np.sum((p<t)&(y==1)) +
                                         fp_cost*np.sum((p>=t)&(y==0)), -t)))


def train(rows, artifact_root, seed=42, review_budget=.02, frozen=None, activate=False, data_kind="synthetic only"):
    if len(rows) < 1000:
        raise ValueError("At least 1000 labelled chronological events are required")
    from .schema import TransactionInput
    canonical=[]
    for row in rows:
        tx=TransactionInput.model_validate({k:v for k,v in row.items() if k not in ("fraud_label","scenario","label_available_at","label_source")})
        if str(row.get("fraud_label")) not in ("0","1"):
            raise ValueError("fraud_label must be 0 or 1")
        payload=tx.payload();payload["amount"]=f"{tx.amount:.2f}"
        from .features import parse_time
        available = parse_time(row.get("label_available_at", payload["timestamp"]))
        if available.tzinfo is None or available < tx.timestamp:
            raise ValueError("Label availability must be timezone-aware and no earlier than the event")
        canonical.append({**payload,"fraud_label":int(row["fraud_label"]),"scenario":row.get("scenario","unspecified"),"label_available_at":available.astimezone(timezone.utc).isoformat(),"label_source":row.get("label_source",data_kind)})
    if len({r["transaction_id"] for r in canonical})!=len(canonical):
        raise ValueError("Training transaction IDs must be unique")
    rows = sorted(canonical, key=lambda r: (r["timestamp"], r["transaction_id"]))
    data_digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    x = pd.DataFrame(feature_rows(rows) if frozen is None else [frozen[r["transaction_id"]] for r in rows])[FEATURES]
    feature_digest=hashlib.sha256(x.to_json(orient="records",double_precision=15).encode()).hexdigest()
    y = np.array([int(r["fraud_label"]) for r in rows])
    n = len(rows)
    a, b, c = int(n*.6), int(n*.7), int(n*.8)
    # Never split a shared timestamp across partitions.
    cuts=[]
    for cut in [a,b,c]:
        while cut<n and rows[cut]["timestamp"]==rows[cut-1]["timestamp"]: cut+=1
        cuts.append(cut)
    a,b,c=cuts
    slices = {"train": slice(0,a), "calibration": slice(a,b), "validation": slice(b,c), "test": slice(c,n)}
    for name, s in slices.items():
        if len(np.unique(y[s])) != 2:
            raise ValueError(f"{name} partition needs both classes; generate more events")
    estimators = {
        "logistic_regression": LogisticRegression(max_iter=1500, class_weight="balanced", random_state=seed),
        "random_forest": RandomForestClassifier(n_estimators=150, max_depth=12, min_samples_leaf=5,
                                                class_weight="balanced", random_state=seed, n_jobs=1),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=15,
                                                                 l2_regularization=2, random_state=seed)}
    # Train/calibration labels must actually have arrived by their partition end.
    from .features import parse_time
    train_ok=np.array([parse_time(r["label_available_at"])<=parse_time(rows[a-1]["timestamp"]) for r in rows[:a]])
    cal_ok=np.array([parse_time(r["label_available_at"])<=parse_time(rows[b-1]["timestamp"]) for r in rows[a:b]])
    if len(np.unique(y[:a][train_ok]))<2 or len(np.unique(y[a:b][cal_ok]))<2:
        raise ValueError("Insufficient mature labels in training/calibration partitions")
    val_ok=np.array([parse_time(r["label_available_at"])<=parse_time(rows[c-1]["timestamp"]) for r in rows[b:c]])
    if len(np.unique(y[b:c][val_ok]))<2:raise ValueError("Insufficient mature validation labels")
    results, bundles, val_predictions = {}, {}, {}
    for name, estimator in estimators.items():
        transform = ColumnTransformer([
            ("numeric", StandardScaler(), NUMERIC),
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL)])
        pipeline = Pipeline([("preprocess", transform), ("classifier", estimator)])
        pipeline.fit(x.iloc[:a].loc[train_ok], y[:a][train_ok])
        raw_cal = pipeline.predict_proba(x.iloc[a:b])[:,1]
        calibrator = LogisticRegression(C=1, random_state=seed).fit(log_odds(raw_cal[cal_ok]), y[a:b][cal_ok])
        bundle = {"pipeline": pipeline, "calibrator": calibrator}
        val_p = probabilities(bundle, x.iloc[b:c])
        threshold = capacity_threshold(val_p,review_budget)
        bundle.update(threshold=threshold, review_budget=review_budget,
                      cold_start_policy="shadow_only_for_fewer_than_5_prior_payments")
        val_predictions[name]=val_p
        bundles[name] = bundle
        results[name] = {"validation": metrics(y[b:c][val_ok], val_p[val_ok], threshold)}
    selected, uncertainty=clustered_comparison(y[b:c][val_ok],{k:p[val_ok] for k,p in val_predictions.items()},np.array([r["payer_id"] for r in rows[b:c]])[val_ok],seed)
    for name in results:
        results[name]["capacity_curve"]=[]
        for budget in (.005,.01,.02,.05,.10,.20):
            t=capacity_threshold(val_predictions[name],budget)
            results[name]["capacity_curve"].append({"validation_budget":budget,"validation":metrics(y[b:c][val_ok],val_predictions[name][val_ok],t)})
    # Selection is frozen before ANY test result is calculated.
    for name, bundle in bundles.items():
        p = probabilities(bundle, x.iloc[c:])
        results[name]["test"] = metrics(y[c:], p, bundle["threshold"])
        for point in results[name]["capacity_curve"]:
            point["test"]=metrics(y[c:],p,point["validation"]["threshold"])
        results[name]["prevalence_scenarios"]=prevalence_table(results[name]["test"]["recall"],results[name]["test"]["false_positive_rate"])
    bundle = bundles[selected]
    test_p = probabilities(bundle, x.iloc[c:])
    seen = {r["payer_id"] for r in rows[:c]}
    new = np.array([r["payer_id"] not in seen for r in rows[c:]])
    unseen = metrics(y[c:][new], test_p[new], bundle["threshold"]) if new.any() else None
    cold=x.iloc[c:]["history_count"].to_numpy()<5
    cold_metrics=metrics(y[c:][cold],test_p[cold],bundle["threshold"]) if cold.any() else None
    # Keep probability metrics honest; policy metrics separately use actual review decisions.
    from sklearn.metrics import confusion_matrix as cmatrix
    policy_pred=(test_p>=bundle["threshold"]) & ~cold
    tn,fp,fn,tp=cmatrix(y[c:],policy_pred,labels=[0,1]).ravel()
    policy_metrics={"alert_rate":float(policy_pred.mean()),"recall":float(tp/max(tp+fn,1)),
                    "precision":float(tp/max(tp+fp,1)),"false_positive_rate":float(fp/max(fp+tn,1)),
                    "confusion_matrix":[[int(tn),int(fp)],[int(fn),int(tp)]],"cold_shadow_count":int(sum(cold))}
    # Unsupervised signal is evaluated independently and never overrides the policy.
    anomaly=IsolationForest(n_estimators=100,contamination="auto",random_state=seed,n_jobs=1)
    anomaly.fit(bundle["pipeline"].named_steps["preprocess"].transform(x.iloc[:a]))
    anomaly_val=-anomaly.score_samples(bundle["pipeline"].named_steps["preprocess"].transform(x.iloc[b:c]))
    anomaly_t=capacity_threshold(anomaly_val,review_budget)
    anomaly_test=-anomaly.score_samples(bundle["pipeline"].named_steps["preprocess"].transform(x.iloc[c:]))
    anomaly_report={"average_precision":float(average_precision_score(y[c:],anomaly_test)),
                    "threshold":anomaly_t,"alert_rate":float(np.mean(anomaly_test>=anomaly_t)),
                    "recall":float(np.mean(anomaly_test[y[c:]==1]>=anomaly_t)),
                    "mode":"shadow signal only; trained on all unlabeled training features"}
    bundle.update(anomaly=anomaly,anomaly_threshold=anomaly_t,
                  explanation_background=x.iloc[:a].sample(min(a,100),random_state=seed).to_dict("records"))
    # Global model reliance, not a per-case causal explanation.
    importance = permutation_importance(bundle["pipeline"], x.iloc[b:c].loc[val_ok], y[b:c][val_ok],
                                       scoring="average_precision", n_repeats=2, random_state=seed)
    digest = hashlib.sha256(f"{data_digest}:{feature_digest}:{FEATURE_VERSION}:{seed}:{sklearn.__version__}:{review_budget}:policy2.1".encode()).hexdigest()
    version = f"v21-{digest[:12]}-{selected}"
    target = Path(artifact_root)/version
    if target.exists():
        raise FileExistsError(f"Immutable version exists: {version}. Use a new artifact root to reproduce.")
    target.mkdir(parents=True)
    bundle.update(version=version, feature_version=FEATURE_VERSION, features=FEATURES)
    joblib.dump(bundle, target/"model.joblib", compress=3)
    from .monitoring import reference_profile
    ref=reference_profile(x.iloc[:a])
    report = {"version":version, "selected_model":selected, "seed":seed,
              "data_kind":data_kind, "feature_version":FEATURE_VERSION,
              "dataset_sha256":data_digest, "created_at":datetime.now(timezone.utc).isoformat(),
              "python":platform.python_version(), "sklearn":sklearn.__version__,
              "selection":uncertainty["selection"], "selection_uncertainty":uncertainty,
              "feature_sha256":feature_digest,"review_budget":review_budget,
              "label_maturity":{"train_used":int(sum(train_ok)),"calibration_used":int(sum(cal_ok)),"validation_used":int(sum(val_ok))},
              "label_sources":{source:sum(r["label_source"]==source for r in rows) for source in sorted({r["label_source"] for r in rows})},
              "policy_test":policy_metrics,"cold_start_test":cold_metrics,"anomaly_test":anomaly_report,
              "ignored_caller_fields":["account_age_days","failed_attempts_1h"],
              "calibration":"Sigmoid fitted on the separate chronological 60-70% partition",
              "threshold_objective":{"validation_alert_budget":review_budget,
                                     "note":"Illustrative review budget; not a throughput guarantee. Cold start is shadow-only. No automatic decline."},
              "splits":{k:{"n":len(rows[s]),"first":rows[s][0]["timestamp"],"last":rows[s][-1]["timestamp"]} for k,s in slices.items()},
              "models":results,"unseen_payers_test":unseen,"test_unseen_payer_count":len({r["payer_id"] for r in rows[c:] if r["payer_id"] not in seen}),
              "permutation_importance":dict(zip(FEATURES, map(float, importance.importances_mean))),
              "reference_features":ref, "model_sha256":file_hash(target/"model.joblib"),
              "limitations":["Synthetic labels are not evidence of real UPI fraud detection.",
                             "Scenario families overlap across time; unseen-payer test is not an unseen-fraud-family test.",
                             "Sequential history uses earlier observed transactions, never their labels.",
                             "Calibration applies only to this data distribution; prevalence projections assume unchanged TPR/FPR.",
                             "Previously inspected synthetic holdout is development evidence; changes are not independent validation.",
                             "Cold-start shadow mode suppresses recommendations and misses fraud; it does not solve cold-start detection.",
                             "Graph patterns are risk signals, not proof of mule activity; simulator does not validate mule detection."]}
    atomic_json(target/"metrics.json", report)
    plot_report(y[c:], test_p, report, target)
    # Save frozen point-in-time training inputs for feedback lineage and exact reuse.
    import csv
    with (target/"training_snapshot.csv").open("w",newline="",encoding="utf-8") as f:
        fields=["transaction_json","features_json","feature_version","fraud_label","label_available_at","source"]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row,features in zip(rows,x.to_dict("records")):
            payload={k:v for k,v in row.items() if k not in ("fraud_label","scenario","label_available_at","label_source")}
            writer.writerow(dict(transaction_json=json.dumps(payload),features_json=json.dumps(features),
                feature_version=FEATURE_VERSION,fraud_label=row["fraud_label"],label_available_at=row["label_available_at"],source=row["label_source"]))
    if activate:atomic_json(Path(artifact_root)/"active.json", {"version":version})
    return report


def plot_report(y, p, report, target):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,3,figsize=(13,3.7),layout="constrained")
    precision, recall, _ = precision_recall_curve(y,p)
    axes[0].plot(recall,precision,color="#168c81");axes[0].axhline(float(np.mean(y)),ls="--",color="#a0a9b5")
    axes[0].set(xlabel="Recall",ylabel="Precision",title="Synthetic holdout: precision–recall")
    fpr,tpr,_=roc_curve(y,p);axes[1].plot(fpr,tpr,color="#5269dc");axes[1].plot([0,1],[0,1],ls="--",color="#a0a9b5")
    axes[1].set(xlabel="False-positive rate",ylabel="True-positive rate",title="ROC curve")
    cm=np.array(report["models"][report["selected_model"]]["test"]["confusion_matrix"])
    axes[2].imshow(cm,cmap="Blues")
    for i in range(2):
        for j in range(2):axes[2].text(j,i,str(cm[i,j]),ha="center",va="center",color="white" if cm[i,j]>cm.max()/2 else "#172033")
    axes[2].set(xticks=[0,1],xticklabels=["Legitimate","Fraud"],yticks=[0,1],yticklabels=["Legitimate","Fraud"],xlabel="Predicted",ylabel="Actual",title="Confusion matrix")
    fig.savefig(target/"evaluation.png",dpi=150);plt.close(fig)


class ModelStore:
    def __init__(self, root, version=None):
        self.root=Path(root);self.bundle=None;self.report=None;self.error=None
        try:
            from .artifact_integrity import read_verified_artifact
            version, report, model_bytes = read_verified_artifact(self.root, version)
            # Deserialize the same bytes that passed preflight, without reopening the path.
            bundle=joblib.load(io.BytesIO(model_bytes))  # Administrator-trusted artifacts only.
            if report["version"]!=version or bundle["version"]!=version:
                raise ValueError("Model version mismatch")
            if bundle["feature_version"]!=FEATURE_VERSION or bundle["features"]!=FEATURES:
                raise ValueError("Feature contract mismatch")
            if not np.isfinite(bundle["threshold"]) or not 0 <= bundle["threshold"] <= np.nextafter(1., np.inf):
                raise ValueError("Invalid model threshold")
            self.bundle,self.report=bundle,report
        except Exception as exc:
            self.error=type(exc).__name__ + ": " + str(exc)

    def score(self, features):
        if self.bundle is None:
            raise RuntimeError("Model unavailable")
        return float(probabilities(self.bundle,pd.DataFrame([features])[FEATURES])[0])


from .monitoring import drift_summary
