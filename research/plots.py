"""Figures derived only from exported tables; no manually inserted results."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LABELS={'static':'Fixed model','weekly_delay0':'Weekly: instant labels',
        'weekly_delay1':'Weekly: 1-week delay','weekly_delay3':'Weekly: 3-week delay',
        'cumulative_delay1':'Cumulative: 1-week delay',
        'static_no_graph':'Fixed: no graph features','static_no_novelty':'Fixed: no novelty features'}
COLORS=['#132d46','#008c95','#5773d6','#df8841','#9156a1','#7c8790','#b46072']


def plot(folder):
    protocol=json.loads((folder/'protocol.json').read_text())
    weekly=pd.read_csv(folder/'weekly_metrics.csv')
    summary=pd.read_csv(folder/'summary.csv')
    monitors=pd.read_csv(folder/'monitoring.csv')
    dest=folder/'figures';dest.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                        'figure.facecolor':'white','axes.facecolor':'white'})
    for model in protocol['models']:
        fig,axes=plt.subplots(1,2,figsize=(12,4.4),sharey=True,layout='constrained')
        for ax,arm in zip(axes,['control','drift']):
            for name,color in zip(list(LABELS)[:5],COLORS):
                d=weekly[(weekly.model==model)&(weekly.arm==arm)&(weekly.strategy==name)]
                if d.empty:continue
                grouped=d.groupby('week').recall
                avg=grouped.mean();se=grouped.std()/np.sqrt(grouped.count())
                ax.plot(avg.index,avg,label=LABELS[name],color=color,lw=1.8)
                ax.fill_between(avg.index,avg-se,avg+se,color=color,alpha=.09)
            for w in [protocol['simulator']['drift_week'],protocol['simulator']['adaptation_week']]:ax.axvline(w,color='#aeb7bf',ls='--',lw=1)
            ax.set(title=f'{arm.capitalize()} arm · {model.upper()}',xlabel='Simulation week (zero-based)',ylim=(0,1),ylabel='Recall at 5% weekly review capacity')
            ax.grid(axis='y',alpha=.15)
        axes[1].legend(fontsize=8,loc='upper right')
        fig.suptitle('Synthetic stress test: adaptation and label delay',fontweight='bold')
        fig.text(.02,-.025,'Lines: mean across seeds; shading: ±1 standard error. Dashed lines mark mix shift and adaptation.',fontsize=8)
        fig.savefig(dest/f'strategies_{model}.png',dpi=170,bbox_inches='tight');plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(10.5,4),layout='constrained')
        for ax,metric in zip(axes,['average_precision','mule_recall']):
            d=summary[(summary.model==model)&(summary.arm=='drift')&(summary.phase=='adapted')&(summary.metric==metric)]
            d=d.set_index('strategy').reindex(['static','static_no_graph','static_no_novelty'])
            ax.bar(np.arange(3),d['mean'],color=[COLORS[0],COLORS[5],COLORS[6]],width=.55)
            ax.set(xticks=range(3),xticklabels=['Full','No graph','No novelty'],ylim=(0,1),title=metric.replace('_',' ').capitalize())
            ax.grid(axis='y',alpha=.15)
        fig.suptitle(f'Adapted phase · fixed-model feature ablations · {model.upper()}',fontweight='bold')
        fig.text(.02,-.025,'Means across seeds. Paired uncertainty is in paired_strategies.csv; absolute differences alone do not establish an effect.',fontsize=8)
        fig.savefig(dest/f'ablations_{model}.png',dpi=170,bbox_inches='tight');plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(10.5,4),layout='constrained')
        for ax,arm in zip(axes,['control','drift']):
            d=monitors[(monitors.model==model)&(monitors.arm==arm)&(monitors.week>=protocol['simulator']['drift_week'])]
            names=['feature_alarm','score_alarm','alert_rate_alarm']
            ax.bar(['Feature\nPSI/KS/JS','Score PSI','Alert rate'],d[names].mean(),color=COLORS[:3],width=.55)
            ax.set(ylim=(0,1),title=arm.capitalize(),ylabel='Fraction of post-shift windows flagged')
            ax.grid(axis='y',alpha=.15)
        fig.suptitle(f'Illustrative distribution alarms · {model.upper()}',fontweight='bold')
        fig.text(.02,-.025,'Stationary-arm alarms estimate background alarms in this simulator. Alarm rate does not measure harm detection.',fontsize=8)
        fig.savefig(dest/f'monitors_{model}.png',dpi=170,bbox_inches='tight');plt.close(fig)
    print('Saved figures:',dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path,nargs='?',default=Path('research/results'))
    plot(p.parse_args().folder)
