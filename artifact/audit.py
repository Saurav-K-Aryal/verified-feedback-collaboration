"""Recheck certificates and recompute frozen study tables without model inference."""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
from .common import ROOT,read_json,read_rows,write_json,write_csv,verify_data,verify_csv,require,safe_output
from . import frozen_core as core

METHODS=('best_independent3','best_validity3','best_counterexample3','mixed_independent3','mixed_counterexample3','matched_independent3','matched_validity3')
COSTS=('prompt_tokens','output_tokens','total_seconds','eval_seconds','prompt_eval_seconds','load_seconds','request_wall_seconds','checker_seconds')

def method_table(rows):
    result=[]
    for method in METHODS+('secondary_one_call',):
        rr=[r for r in rows if r['method']==method]
        x={'method':method,'n':len(rr),'solved':sum(r['accepted'] for r in rr),'solve_rate':sum(r['accepted'] for r in rr)/len(rr),
            'scheduled_calls':sum(r['scheduled_calls'] for r in rr),'request_errors':sum(r['request_errors'] for r in rr)}
        for field in COSTS:
            values=[r[field] for r in rr if r[field] is not None]
            x['mean_'+field]=sum(values)/len(values) if values else None;x['missing_'+field]=len(rr)-len(values)
        result.append(x)
    return result

def run(output,verify=False,plots=True):
    output=safe_output(output);output.mkdir(parents=True,exist_ok=True);checksum_files=verify_data()
    manifest=read_json('data/tasks.json.gz');tasks={t['task_id']:t for phase in manifest.values() for t in phase}
    raw=read_rows('data/calls.jsonl.gz');calls={r['uid']:r for r in raw}
    require(len(calls)==len(raw)==3824,'Unexpected/duplicate physical calls')
    error_count=0
    for row in raw:
        if row['verdict']['kind']=='request_error':
            error_count+=1;require(not row['verdict']['accepted'],'Serving error cannot be accepted');continue
        response=row['response'];got=core.check_candidate(tasks[row['task_id']],response.get('text',''),done=response.get('done',False),finish_reason=response.get('finish_reason','unknown'))
        require(got==row['verdict'],'Frozen checker mismatch at '+row['uid'])
    stored=read_json('data/portfolios.json.gz');rows=[]
    for old in stored:
        row=core.portfolio(tasks[old['task_id']],old['method'],[calls[u] for u in old['candidate_uids']])
        require(row==old,'Portfolio/cost reconstruction mismatch');rows.append(row)
    require(len(rows)==256*7,'Incomplete test portfolios')
    dev=read_json('data/development_portfolios.json.gz');selection=read_json('data/development_selection.json')
    models=list(read_json('provenance/generation_models.json'))
    for row in dev:
        computed=core.portfolio(tasks[row['task_id']],row['method'],[calls[u] for u in row['candidate_uids']])
        require(all(row[k]==v for k,v in computed.items()),'Development portfolio differs')
    for strategy in ['independent','validity','counterexample']:
        counts={m:sum(r['accepted'] for r in dev if r['method']==strategy and r['selection_model']==m) for m in models}
        selected=max(models,key=lambda m:(counts[m],-models.index(m)))
        require(selected==selection['selected'][strategy],'Development selection mismatch')
    initial_model=selection['selected']['independent']
    initial=[r for r in raw if r['phase']=='test' and r['model']==initial_model and '/ind/' in r['uid'] and r['uid'].endswith('/0')]
    require(len(initial)==256,'Initial one-call baseline incomplete')
    rows += [core.portfolio(tasks[r['task_id']],'secondary_one_call',[r]) for r in initial]
    methods=method_table(rows);family=[]
    for fam in ['directed_path','boolean_program']:
        for grade in range(3):
            for method in METHODS:
                rr=[r for r in rows if r['family']==fam and r['regime']==f'grade_{grade}' and r['method']==method]
                family.append({'family':fam,'grade':grade,'method':method,'n':len(rr),'solved':sum(r['accepted'] for r in rr),'solve_rate':sum(r['accepted'] for r in rr)/len(rr)})
    comparisons=[]
    for baseline in ['best_independent3','best_validity3']:
        r=core.conservative_comparison(rows,'best_counterexample3',baseline)
        comparisons.append({'method':r['method'],'baseline':baseline,'n':r['n'],'difference':r['difference'],'interval_level':r['interval_level'],
            'lower':r['conservative_paired_interval'][0],'upper':r['conservative_paired_interval'][1],
            'above_five_point_margin':r['above_five_point_margin'],'frozen_comparison_valid':error_count==0})
    exact=sum(core.check_candidate(t,core.canonical(core.exact_solve(t)))['accepted'] for t in manifest['test'])
    old_tasks={t['task_id']:t for ts in read_json('data/original_pilot_tasks.json.gz').values() for t in ts}
    diagnostic=[core.diagnose_candidate(old_tasks[r['task_id']],r) for r in read_rows('data/original_pilot_test_calls.jsonl.gz')]
    replacement=read_json('data/diagnostics/model_replacement.json')
    response=replacement['result']['response'];verdict=core.check_candidate(replacement['protocol']['task'],response['text'],done=response['done'],finish_reason=response['finish_reason'])
    require(verdict==replacement['result']['verdict'] and not verdict['accepted'],'Separate replacement-model check changed')
    require(replacement['result']['original_observation_replaced'] is False,'Replacement diagnostic cannot enter frozen results')
    write_json(output/'separate_replacement_diagnostic.json',{'model':replacement['result']['model'],'task_id':replacement['result']['task_id'],'rechecked_verdict':verdict,'included_in_frozen_study_counts':False})
    summary={'physical_calls':len(raw),'test_tasks':len(manifest['test']),'request_errors':error_count,
        'first_call_solved':sum(r['verdict']['accepted'] for r in initial),'exact_solver_solved':exact,'scientific_comparison_valid':error_count==0,
        'method_solved':{r['method']:r['solved'] for r in methods if r['method'] in METHODS},'retrospective_test_candidates':len(diagnostic),
        'retrospective_normalizations':sum(r['normalization_attempted'] for r in diagnostic),
        'retrospective_recovered_certificates':sum(r['recoverable_complete_certificate'] for r in diagnostic)}
    for name,table in [('method_results',methods),('family_grade_results',family),('primary_comparisons',comparisons)]:write_csv(output/(name+'.csv'),table)
    write_json(output/'summary.json',summary);write_json(output/'retrospective_diagnostic.json',{'counts':dict(Counter(r['category'] for r in diagnostic)),'records':diagnostic})
    if verify:
        require(summary==read_json('results/reference/summary.json'),'Reference summary mismatch')
        for name,keys in [('method_results',['method']),('family_grade_results',['family','grade','method']),('primary_comparisons',['method','baseline'])]:verify_csv(output/(name+'.csv'),ROOT/f'results/reference/{name}.csv',keys)
    if plots:_plots(output,methods,family,comparisons)
    write_json(output/'AUDIT_STATUS.json',{'status':'passed','evidence_checksums':checksum_files,'all_nonerror_call_verdicts_rechecked':len(raw)-error_count,
        'all_portfolios_reconstructed':len(rows),'reference_tables_checked':verify,'new_model_inference':False,
        'primary_interpretation':'Original request error retained; frozen scientific comparison is ineligible. Bounds and counts remain descriptive.',
        'recovery':read_json('provenance/recovery_observation.json')['status']})
    return summary

def _plots(out,methods,family,comparisons):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names={'best_independent3':'Independent','best_validity3':'Validity feedback','best_counterexample3':'Counterexample feedback','mixed_independent3':'Mixed independent','mixed_counterexample3':'Mixed counterexample','secondary_one_call':'One call (secondary)'}
    rr=[r for r in methods if r['method'] in names]
    fig,ax=plt.subplots(figsize=(7.2,3.2));ax.barh([names[r['method']] for r in rr],[100*r['solve_rate'] for r in rr],color='white',edgecolor='black',hatch='//')
    ax.set(xlabel='Exactly verified task success (%)',xlim=(0,100),title='Descriptive outcomes; frozen comparison ineligible')
    for i,r in enumerate(rr):ax.text(100*r['solve_rate']+1,i,f'{r["solved"]}/{r["n"]}',va='center',fontsize=9)
    fig.tight_layout();fig.savefig(out/'solve_rates.pdf');fig.savefig(out/'solve_rates.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(6.8,2.8))
    for i,r in enumerate(comparisons):ax.errorbar(r['difference']*100,i,xerr=[[(r['difference']-r['lower'])*100],[(r['upper']-r['difference'])*100]],fmt='ko',capsize=4)
    ax.axvline(5,color='black',linestyle='--');ax.set_ylim(-.5,1.5);ax.set_yticks(range(2),['Counterexample − independent','Counterexample − validity']);ax.set_xlabel('Paired difference and conservative 97.5% bounds (points)');ax.set_title('Frozen bounds; no superiority established')
    fig.tight_layout();fig.savefig(out/'paired_bounds.pdf');plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'results/recomputed');p.add_argument('--verify',action='store_true');p.add_argument('--no-plots',action='store_true');args=p.parse_args()
    print(run(args.output,args.verify,not args.no_plots))
