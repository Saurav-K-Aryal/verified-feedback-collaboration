"""Portable recheck of a separately exported complete study, without inference.

The study bundle uses the same data/provenance/reference layout as the original
artifact. Follow-up evidence is kept separate and cannot replace original rows.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json
from collections import Counter
from pathlib import Path
from .common import require,safe_output,write_csv,write_json,verify_csv
from . import frozen_core as core
from .audit import METHODS,method_table

STRATEGIES=('independent','validity','counterexample')
FAMILIES=('directed_path','boolean_program')

def run(study,output,verify=False):
    study=Path(study).resolve();output=safe_output(output)
    require(study!=output and study not in output.parents and output not in study.parents,
            'Study inputs and output must not overlap')
    def load(name):
        path=study/name
        with (gzip.open(path,'rt',encoding='utf-8') if path.suffix=='.gz' else path.open()) as stream:return json.load(stream)
    def rows(name):
        with gzip.open(study/name,'rt',encoding='utf-8') as stream:return [json.loads(line) for line in stream if line.strip()]
    checks=load('data/SHA256SUMS.json')
    for name,expected in checks.items():
        path=(study/name).resolve()
        require(study in path.parents,'Checksum path escapes study')
        require(hashlib.sha256(path.read_bytes()).hexdigest()==expected,'Checksum mismatch: '+name)
    manifest=load('data/tasks.json.gz');tasks={t['task_id']:t for values in manifest.values() for t in values}
    require(len(tasks)==sum(map(len,manifest.values())),'Duplicate task id')
    raw=rows('data/calls.jsonl.gz');calls={r['uid']:r for r in raw}
    require(len(calls)==len(raw),'Duplicate physical call')
    for row in raw:
        require(row['task_id'] in tasks,'Call refers to unknown task')
        if row['verdict']['kind']=='request_error':
            require(not row['verdict']['accepted'],'Serving error marked accepted');continue
        response=row['response']
        verdict=core.check_candidate(tasks[row['task_id']],response.get('text',''),done=response.get('done',False),finish_reason=response.get('finish_reason','unknown'))
        require(verdict==row['verdict'],'Verifier mismatch: '+row['uid'])
    portfolios=load('data/portfolios.json.gz');dev=load('data/development_portfolios.json.gz')
    for row in portfolios+dev:
        actual=core.portfolio(tasks[row['task_id']],row['method'],[calls[uid] for uid in row['candidate_uids']])
        require(all(row[key]==value for key,value in actual.items()),'Portfolio or cost mismatch')
    require(len(portfolios)==len(manifest['test'])*len(METHODS),'Test portfolios incomplete')
    require(Counter((r['task_id'],r['method']) for r in portfolios)==Counter((t['task_id'],m) for t in manifest['test'] for m in METHODS),'Unexpected test portfolio assignment')
    selection=load('data/development_selection.json');models=[r['model'] for r in selection['scores']]
    require(len(models)==3 and len(set(models))==3,'Expected three distinct configurations')
    require(set(models)==set(load('provenance/generation_models.json')),'Model manifest mismatch')
    require(Counter((r['task_id'],r['method'],r['selection_model']) for r in dev)==Counter((t['task_id'],s,m) for t in manifest['development'] for s in STRATEGIES for m in models),'Development portfolios incomplete')
    counts={s:{m:sum(r['accepted'] for r in dev if r['method']==s and r['selection_model']==m) for m in models} for s in STRATEGIES}
    selected={s:max(models,key=lambda m:(counts[s][m],-models.index(m))) for s in STRATEGIES}
    require(selection['selected']==selected,'Development model selection mismatch')
    expected_order=sorted(models,key=lambda m:(-counts['counterexample'][m],-counts['independent'][m],models.index(m)))
    require(selection['mixed_order']==expected_order,'Mixed model order mismatch')
    grade_rows=[];informative={f:False for f in FAMILIES};syntax={}
    for family in FAMILIES:
        for grade in range(3):
            for strategy in STRATEGIES:
                rr=[r for r in dev if r['family']==family and r['regime']==f'grade_{grade}' and r['method']==strategy and r['selection_model']==selected[strategy]]
                n=len(rr);solved=sum(r['accepted'] for r in rr);intermediate=n==8 and 1<=solved<=7
                informative[family]|=intermediate
                grade_rows.append(dict(family=family,grade=grade,strategy=strategy,n=n,solved=solved,intermediate=intermediate))
        rr=[r for r in raw if r['phase']=='development' and tasks[r['task_id']]['family']==family]
        syntax[family]={'n':len(rr),'well_formed':sum(r['verdict']['kind'] not in {'malformed','incomplete','truncated','request_error'} for r in rr)}
    dev_errors=sum(r['phase']=='development' and r['verdict']['kind']=='request_error' for r in raw)
    gate_met=all(informative.values()) and all(r['n'] and r['well_formed']/r['n']>=.5 for r in syntax.values()) and dev_errors==0
    gate=load('data/development_gate.json')
    require(gate['grade_results']==grade_rows and gate['well_formed']==syntax and gate['request_errors']==dev_errors,'Gate evidence differs')
    require(gate.get('original_gate_conditions_met',gate['eligible'])==gate_met,'Gate eligibility differs')
    initial=[r for r in raw if r['phase']=='test' and r['model']==selected['independent'] and '/ind/' in r['uid'] and r['uid'].endswith('/0')]
    require(Counter(r['task_id'] for r in initial)==Counter(t['task_id'] for t in manifest['test']),'One-call baseline incomplete')
    all_rows=portfolios+[core.portfolio(tasks[r['task_id']],'secondary_one_call',[r]) for r in initial]
    methods=method_table(all_rows);family_rows=[]
    for family in FAMILIES:
        for grade in range(3):
            for method in METHODS:
                rr=[r for r in portfolios if r['family']==family and r['regime']==f'grade_{grade}' and r['method']==method]
                require(bool(rr),'Missing family/grade cell')
                family_rows.append(dict(family=family,grade=grade,method=method,n=len(rr),solved=sum(r['accepted'] for r in rr),solve_rate=sum(r['accepted'] for r in rr)/len(rr)))
    error_count=sum(r['verdict']['kind']=='request_error' for r in raw)
    provenance=load('provenance/run.json');followup=bool(provenance.get('post_study_replacement',False))
    valid=not followup and gate_met and error_count==0 and bool(provenance['scientific_comparison_valid'])
    comparisons=[]
    for baseline in ['best_independent3','best_validity3']:
        row=core.conservative_comparison(all_rows,'best_counterexample3',baseline)
        comparisons.append(dict(method=row['method'],baseline=baseline,n=row['n'],difference=row['difference'],interval_level=row['interval_level'],lower=row['conservative_paired_interval'][0],upper=row['conservative_paired_interval'][1],above_five_point_margin=row['above_five_point_margin'],frozen_comparison_valid=valid))
    exact=sum(core.check_candidate(t,core.canonical(core.exact_solve(t)))['accepted'] for t in manifest['test'])
    summary=dict(physical_calls=len(raw),test_tasks=len(manifest['test']),request_errors=error_count,first_call_solved=sum(r['verdict']['accepted'] for r in initial),exact_solver_solved=exact,scientific_comparison_valid=valid,original_gate_conditions_met=gate_met,post_study_replacement=followup,method_solved={r['method']:r['solved'] for r in methods if r['method'] in METHODS},selected_models=selected)
    output.mkdir(parents=True,exist_ok=True)
    tables={'method_results':methods,'family_grade_results':family_rows,'primary_comparisons':comparisons}
    for name,table in tables.items():write_csv(output/(name+'.csv'),table)
    write_json(output/'summary.json',summary)
    if verify:
        for name,keys in [('method_results',['method']),('family_grade_results',['family','grade','method']),('primary_comparisons',['method','baseline'])]:verify_csv(output/(name+'.csv'),study/f'results/reference/{name}.csv',keys)
    write_json(output/'AUDIT_STATUS.json',{'status':'passed','evidence_checksums':len(checks),'reference_tables_checked':verify,'all_nonerror_verdicts_rechecked':len(raw)-error_count,'scientific_comparison_valid':valid,'post_study_replacement':followup,'new_model_inference':False,'interpretation':'A reused-panel post-study follow-up is descriptive even when its execution has no serving errors.' if followup else 'Original frozen eligibility rule retained.'})
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--study',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    print(run(args.study,args.output,args.verify))
