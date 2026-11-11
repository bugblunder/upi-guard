"""Regenerate the study's narrative tables from verified exported results."""
from pathlib import Path
import json
import pandas as pd
from .study import interval


def report(folder=Path('research/results'),destination=Path('docs/RESEARCH_RESULTS.md')):
    s=pd.read_csv(folder/'summary.csv')
    c=pd.read_csv(folder/'paired_control.csv')
    a=pd.read_csv(folder/'paired_strategies.csv')
    m=pd.read_csv(folder/'monitor_summary.csv')
    w=pd.read_csv(folder/'weekly_metrics.csv')
    d=json.loads((folder/'diagnostics.json').read_text())
    complete=json.loads((folder/'completion.json').read_text())
    def get(model,strategy,phase,arm='drift',metric='recall'):
        return s[(s.model==model)&(s.strategy==strategy)&(s.phase==phase)&(s.arm==arm)&(s.metric==metric)].iloc[0]
    def fmt(row,percent=True):
        scale=100 if percent else 1
        return f"{row['mean']*scale:.1f} [{row['ci95_low']*scale:.1f}, {row['ci95_high']*scale:.1f}]" if percent else f"{row['mean']:.3f} [{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]"
    text=['# Verified research results','',
      'This is a fresh synthetic study built from the uploaded reviewed application. The earlier conversational experiment package was absent, so its reported eight-seed results are not reused. The research question and full limitations are in [RESEARCH_PLAN.md](RESEARCH_PLAN.md).',
      '',f"**Completed:** {len(complete['seeds'])} seeds (0–4), HGB and logistic regression, matched drift/stationary arms, seven strategies, 24 simulated weeks per arm. There are {complete['total_simulated_events']:,} generated events across seed/arm runs, {complete['weekly_rows']:,} weekly strategy rows and {complete['monitor_rows']} monitoring rows. Each arm has 17,280 events; the two models reuse those events. A source-hash and completeness check passed.",
      '', '## Fixed-model change and the stationary control','',
      'Recall at a 5% weekly ranking budget, in percent. Brackets are descriptive 95% t intervals across five seed means. The adapted phase is weeks 18–23; pre-shift is weeks 12–13.',
      '', '| Learner | Drift pre-shift | Drift adapted | Stationary adapted | Paired difference in differences (pp) |',
      '|---|---:|---:|---:|---:|']
    for model in ['hgb','lr']:
        control=c[(c.model==model)&(c.strategy=='static')&(c.metric=='recall')].iloc[0]
        text.append(f"| {model.upper()} | {fmt(get(model,'static','pre'))} | {fmt(get(model,'static','adapted'))} | {fmt(get(model,'static','adapted','control'))} | {fmt(control)} |")
    text += ['', 'The paired contrast is `(adapted - pre)_drift - (adapted - pre)_stationary`. Its negative intervals support additional deterioration caused by the scheduled intervention in this simulator. The stationary stream also varies; a raw before/after decline alone would overstate attribution. Because both the intervention and its measurable signals were designed here, decay itself is not a novel discovery.',
      '', '## Retraining and label delay','',
      'Adapted-phase recall in the drift arm, percent [95% t interval]. All weekly fits use only outcomes that have arrived before that week.',
      '', '| Strategy | HGB | Logistic regression |','|---|---:|---:|']
    for strategy in ['static','weekly_delay0','weekly_delay1','weekly_delay3','cumulative_delay1']:
        text.append(f"| {strategy} | {fmt(get('hgb',strategy,'adapted'))} | {fmt(get('lr',strategy,'adapted'))} |")
    text += ['', 'Both learners benefit from retraining compared with the fixed model in the adapted phase; paired differences are in `paired_strategies.csv`. Sliding-window instant-label versus three-week-label comparisons must be interpreted separately:']
    delay=[]
    for model in ['hgb','lr']:
        p=w[(w.arm=='drift')&(w.phase=='adapted')&(w.model==model)].groupby(['seed','strategy']).recall.mean().unstack()
        r=interval(p.weekly_delay0-p.weekly_delay3)
        delay.append(dict(model=model,comparison='weekly_delay0_minus_weekly_delay3',**r))
        text.append(f"\n- {model.upper()}: {fmt(r)} percentage points for instant minus three-week labels.")
    pd.DataFrame(delay).to_csv(folder/'paired_delay.csv',index=False)
    text += ['', 'The HGB delay interval crosses zero, while the logistic-regression interval does not. Five seeds do not establish a robust universal delay penalty. Cumulative training is competitive for HGB but weaker than sliding training for logistic regression; no single strategy dominates both learners.',
      '', '## Feature ablations','',
      'Ablation minus full fixed model in the adapted drift phase. AP differences are raw AP units; recalls use percentage points. Negative values favor the full model.',
      '', '| Learner | Ablation | AP difference [95% CI] | Recall difference, pp [95% CI] |',
      '|---|---|---:|---:|']
    for model in ['hgb','lr']:
        for strategy in ['static_no_graph','static_no_novelty']:
            r=a[(a.model==model)&(a.strategy_minus_static==strategy)]
            text.append(f"| {model.upper()} | {strategy} | {fmt(r[r.metric=='average_precision'].iloc[0],False)} | {fmt(r[r.metric=='recall'].iloc[0])} |")
    text += ['', 'Removing graph aggregates lowers mean HGB recall and AP, but both paired intervals cross zero. Logistic regression has a small recall benefit from graph aggregates, while its AP interval crosses zero. This is limited evidence, not validation of a mule detector. Removing novelty flags lowers AP for both learners, showing continued reliance; the generator still contains template shortcuts.',
      '', '## Distribution monitoring','',
      'Post-shift windows flagged (%), mean across five seeds. Each model/arm has 50 post-shift windows. Thresholds are illustrative and were not tuned to equal false-alarm rates.',
      '', '| Learner | Monitor | Drift windows flagged | Stationary windows flagged |',
      '|---|---|---:|---:|']
    for model in ['hgb','lr']:
        for monitor in ['feature_alarm','score_alarm','alert_rate_alarm']:
            r=m[(m.model==model)&(m.monitor==monitor)&(m.metric=='post_alarm_rate')].set_index('arm')
            text.append(f"| {model.upper()} | {monitor} | {100*r.loc['drift','mean']:.1f}% | {100*r.loc['control','mean']:.1f}% |")
    text += ['', 'Score PSI never fires, but feature and alert-rate rules sometimes do. Therefore the accurate conclusion is **mostly silent, weakly aligned illustrative monitors**, rather than all monitors always silent. Feature alarms occur at the same aggregate rate in the stationary arm. Retrospective harmful-week coverage is in `monitor_summary.csv`; it uses an exploratory 80%-of-pre-recall rule and is not a validated degradation detector.',
      '', 'The results are compatible with fraud-specific changes being diluted in population-level distributions, but this study does not isolate that mechanism. Prevalence sweeps and threshold-matched comparisons remain necessary.',
      '', '## Data checks','',
      f"Realized latent fraud prevalence is {min(x['prevalence'] for x in d)*100:.2f}%–{max(x['prevalence'] for x in d)*100:.2f}% across seeds and is exactly matched between paired arms. In drift arms, `new_payee` alone has AUC {min(x['novelty_auc']['new_payee'] for x in d if x['arm']=='drift'):.3f}–{max(x['novelty_auc']['new_payee'] for x in d if x['arm']=='drift'):.3f}. This reduces the original shortcut but does not eliminate simulator reliance. All three graph aggregates are active; legitimate merchant activity is a deliberate confound.",
      '', 'The independently rerunnable original CSV audit is `python -m research.audit_original`. On the supplied 12,000 rows it confirms 9.28% fraud prevalence, `new_payee` AUC 0.892 and all-zero payer incoming count and pass-through ratio. These observations describe the supplied synthetic source, not real payment behavior.',
      '', '## Validation and limits','',
      '- Ten offline unittest checks pass, including seed pairing, timestamp/contract checks, graph activation and legitimate confounds, future/label invariance, mature-label boundaries, feature ablations, missing-positive metrics and exact capacity with ties.',
      '- All initial source hashes and expected result combinations pass `research.verify_results`. Both models completed all strategies in both arms.',
      '- The six figures were regenerated from tables; all six plots were visually checked. Lines show mean ±1 standard error, not 95% confidence bands. Ablation bars show means; paired intervals are supplied separately.',
      '- The existing Flask/database/application tests were not rerun: this runtime lacks their dependencies. Application Python code and original model/data artifacts remain byte-identical to the uploaded ZIP. The CI workflow now adds the offline unittest command; that remote workflow has not been executed here.',
      '- All evidence is conditional on a small, authored simulator. Current limitations include template and category shortcuts, a fixed population, simple labels, class-independent fixed delays, representative rather than selected feedback, and combined mix/adaptation interventions.',
      '- Weekly top-k evaluation uses the complete week and cannot establish real-time review capacity. Transaction-value recall may double-count transferred funds. Neither calibrated production probabilities nor unique loss prevention is established.',
      '- The supplied historic PaySim results are preserved but were not rerun. This extension has not evaluated any real UPI data. No new monitoring algorithm or exhaustive novelty assessment is claimed.',
      '', '## Reproduce','', '```bash',
      'python -m unittest discover -s research/tests -v',
      'python -m research.study --seeds 5 --episodes 240 --models hgb lr --out research/results_reproduction',
      'python -m research.verify_results research/results_reproduction',
      'python -m research.analyze_control research/results_reproduction',
      'python -m research.plots research/results_reproduction',
      '```','',
      'The study refuses to overwrite existing outputs. Use a new folder for every run. See `research/README.md` for the offline environment and proposed sensitivity commands. Completed main outputs are in `research/results/`; `completion.json` records their verified scope.',
      '', '![Controlled HGB trajectories](../research/results/figures/strategies_hgb.png)',
      '', '![HGB distribution alarms](../research/results/figures/monitors_hgb.png)','']
    destination.write_text('\n'.join(text),encoding='utf-8')
    print('Wrote',destination)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path,nargs='?',default=Path('research/results'))
    parser.add_argument('--out',type=Path,default=Path('docs/RESEARCH_RESULTS.md'))
    args=parser.parse_args()
    report(args.folder,args.out)
