"""Per-case SHAP attributions of the fitted model, separate from policy rules."""
import numpy as np
import pandas as pd
from scipy.special import expit
from .features import FEATURES, NUMERIC, CATEGORICAL
from .ml import probabilities


def explain(bundle,features):
    import shap
    pipeline=bundle['pipeline'];transform=pipeline.named_steps['preprocess'];est=pipeline.named_steps['classifier']
    frame=pd.DataFrame([features])[FEATURES]
    z=transform.transform(frame)
    background=transform.transform(pd.DataFrame(bundle['explanation_background'])[FEATURES])
    if hasattr(est,'coef_'):
        ex=shap.LinearExplainer(est,background)(z)
        # Calibration is affine in the classifier log odds, so this is exact.
        scale=float(bundle['calibrator'].coef_[0,0]);offset=float(bundle['calibrator'].intercept_[0])
        values=np.asarray(ex.values)[0]*scale
        base=float(np.asarray(ex.base_values).ravel()[0])*scale+offset
        units='calibrated_log_odds';reconstructed=float(expit(base+values.sum()))
    else:
        ex=shap.TreeExplainer(est,data=background,feature_perturbation='interventional')(z)
        values=np.asarray(ex.values);base=np.asarray(ex.base_values)
        if values.ndim==3: # random forest output is class probability
            values=values[0,:,1];base=float(base[0,1]);units='uncalibrated_probability'
            raw=float(np.clip(base+values.sum(),1e-6,1-1e-6))
            reconstructed=float(bundle['calibrator'].predict_proba([[np.log(raw/(1-raw))]])[0,1])
        else: # gradient boosting raw margin is log odds
            scale=float(bundle['calibrator'].coef_[0,0]);offset=float(bundle['calibrator'].intercept_[0])
            values=values[0]*scale;base=float(base.ravel()[0])*scale+offset
            units='calibrated_log_odds';reconstructed=float(expit(base+values.sum()))
    names=list(NUMERIC)
    encoder=transform.named_transformers_['categorical']
    for name,categories in zip(CATEGORICAL,encoder.categories_):names.extend([name]*len(categories))
    aggregated={name:0. for name in FEATURES}
    for name,value in zip(names,values):aggregated[name]+=float(value)
    probability=float(probabilities(bundle,frame)[0])
    residual=abs(reconstructed-probability)
    if residual>1e-4:raise ValueError('SHAP reconstruction failed')
    return {'method':'SHAP','units':units,'base_value':base,'contributions':aggregated,
            'calibrated_probability':probability,'reconstructed_probability':reconstructed,
            'reconstruction_error':residual,'model_version':bundle['version'],
            'note':'Association with this fitted model and training background, not causation or proof of fraud. Tree probability contributions precede sigmoid calibration.'}
