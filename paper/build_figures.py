"""Render monochrome paper figures from the audited, bundled numeric summaries."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / 'figure_data.json').read_text())
OUT = HERE / 'figures'
OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8,
    'axes.titlesize': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7,
    'ytick.labelsize': 7, 'legend.fontsize': 7, 'pdf.fonttype': 42,
    'axes.spines.top': False, 'axes.spines.right': False})

def save(fig, name):
    fig.savefig(OUT / (name + '.pdf'), bbox_inches='tight', pad_inches=.035)
    fig.savefig(OUT / (name + '.png'), dpi=240, bbox_inches='tight', pad_inches=.035)
    plt.close(fig)

if 'primary_comparisons' in DATA:
    fig, ax = plt.subplots(figsize=(7.0, 1.85), layout='constrained')
    for i, row in enumerate(DATA['primary_comparisons']):
        x, lo, hi = [100 * float(row[k]) for k in ('difference', 'lower', 'upper')]
        y = 1 - i
        ax.errorbar(x, y, xerr=[[x-lo], [hi-x]], fmt='o', color='black',
                    markerfacecolor='white', markersize=5, capsize=3, lw=1)
        ax.text(hi+1, y, f'{x:+.2f} pp', va='center', fontsize=8)
    ax.axvline(0, color='.4', lw=.7)
    ax.axvline(5, color='black', lw=.9, ls='--', label='Required +5 pp margin')
    ax.set_yticks([1, 0], ['Exact minus independent', 'Exact minus validity-only'])
    ax.set_xlim(-23, 43); ax.set_ylim(-.65, 1.5)
    ax.set_xlabel('Paired solve-rate difference (percentage points)')
    ax.legend(loc='lower right', frameon=False)
    save(fig, 'topic3_primary_comparisons')
    methods = {r['method']: r for r in DATA['method_results']}
    selected = [('best_independent3', 'Independent'), ('best_validity3', 'Validity'),
                ('best_counterexample3', 'Exact feedback'),
                ('mixed_independent3', 'Mixed independent'),
                ('mixed_counterexample3', 'Mixed exact feedback')]
    fig, (left, right) = plt.subplots(1, 2, figsize=(7, 2.55), layout='constrained', gridspec_kw={'width_ratios': [1.45, 1]})
    y = np.arange(len(selected))
    left.barh(y, [float(methods[k]['solve_rate'])*100 for k, _ in selected], facecolor='white', edgecolor='black', hatch='//', height=.58)
    for i,(key,_) in enumerate(selected):
        r=methods[key];left.text(float(r['solve_rate'])*100+.8, i, f"{r['solved']}/{r['n']}", va='center', fontsize=7)
    left.set_yticks(y, [label for _,label in selected]);left.invert_yaxis();left.set_xlim(0, 60)
    left.set_xlabel('Solved tasks (%)');left.set_title('Three-call strategies')
    right.barh(y, [float(methods[k]['mean_request_wall_seconds']) for k,_ in selected],facecolor='.75',edgecolor='black',height=.58)
    for i,(key,_) in enumerate(selected):
        value=float(methods[key]['mean_request_wall_seconds']);right.text(value+.06,i,f'{value:.2f}',va='center',fontsize=7)
    right.set_yticks(y, []);right.invert_yaxis();right.set_xlim(0, 5.4)
    right.set_xlabel('Mean charged request wall time (s)');right.set_title('Observed server costs')
    save(fig, 'topic3_quality_cost')
else:
    panel = ['word_tfidf','char_tfidf','length_style','historical_word','binoculars','fastdetectgpt','radar']
    labels = ['Word TF-IDF','Character TF-IDF','Length/style','Historical word','Binoculars','Fast-DetectGPT','RADAR']
    models = ['qwen3.5:4b','llama3.1:8b','gemma4:12b']
    short = ['Qwen','Llama','Gemma']
    cells=DATA['cell_metrics']
    fig, axs=plt.subplots(2,4,figsize=(7.1,3.9),layout='constrained')
    for ax,detector,title in zip(axs.flat,panel,labels):
        matrix=np.zeros((3,3))
        for i,parent in enumerate(models):
            for j,child in enumerate(models):
                rr=[r for r in cells if r['condition']=='rewrite' and r['detector']==detector and r['source_model']==parent and r['model']==child]
                assert len(rr)==3 and sum(int(r['n']) for r in rr)==450
                matrix[i,j]=100*sum(int(r['flagged']) for r in rr)/450
        ax.imshow(matrix,cmap='Greys',vmin=0,vmax=100)
        for i in range(3):
            for j in range(3):
                value=matrix[i,j];label=f'{value:.1f}' if value<100 else '100'
                ax.text(j,i,label,ha='center',va='center',fontsize=7.5,color='white' if value>55 else 'black')
        ax.set_title(title,pad=4);ax.set_xticks(range(3),short);ax.set_yticks(range(3),short)
        ax.tick_params(length=0)
        for spine in ax.spines.values():spine.set_visible(False)
    axs.flat[-1].axis('off')
    axs.flat[-1].text(.02,.7,'Cells: flagged (%)\nRows: parent model\nColumns: rewriter\n450 pairs per cell\n\nDiagonal: same-model\nrewrite controls',fontsize=7.5,va='top',linespacing=1.45)
    save(fig,'rewrite_matrix_all')
    totals={r['detector']:r for r in DATA['all_comparators']}
    fig,axs=plt.subplots(1,2,figsize=(7.0,2.55),layout='constrained',sharey=True)
    y=np.arange(7)
    for ax,key,title,marker in zip(axs,['human_fpr','direct_detection_rate'],['Human false-positive rate','Direct-generation flag rate'],['o','s']):
        x=[100*float(totals[d][key]) for d in panel]
        ax.scatter(x,y,marker=marker,facecolor='white',edgecolor='black',s=25,zorder=3)
        for i,v in enumerate(x):
            ax.text(v+3 if v<90 else v-3,i,f'{v:.1f}%',va='center',ha='left' if v<90 else 'right',fontsize=7)
        ax.set_title(title);ax.set_xlim(-2,108);ax.set_xticks([0,25,50,75,100]);ax.grid(axis='y',color='.9',lw=.5)
        ax.set_xlabel('Rate (%)');ax.set_yticks(y,labels)
    axs[0].invert_yaxis()
    save(fig,'detector_operating_points')
    fig,ax=plt.subplots(figsize=(3.35,2.55),layout='constrained')
    conditions=['direct','rewrite','human_rewrite'];names=['Direct','Model rewrite','Human-text rewrite']
    for c,(cond,name,hatch) in enumerate(zip(conditions,names,['','//','..'])):
        values=[]
        for model in models:
            r=next(r for r in DATA['length_diagnostics'] if r['source']=='all' and r['condition']==cond and r['model']==model)
            values.append(100*float(r['length_pass_fraction']))
        xx=np.arange(3)+(c-1)*.24
        ax.bar(xx,values,width=.23,label=name,facecolor='white',edgecolor='black',hatch=hatch,lw=.7)
    ax.set_xticks(range(3),short);ax.set_ylim(0,104);ax.set_ylabel('Length-contract pass rate (%)')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.31),ncol=1,frameon=False,handlelength=1.5,labelspacing=.2)
    save(fig,'length_compliance')
