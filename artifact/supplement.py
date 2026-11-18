"""Recompute a descriptive cost/repeatability supplement from supplied evidence."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from pathlib import Path
from .common import ROOT,read_rows,require,safe_output,verify_data,write_json

COSTS=('prompt_tokens','output_tokens','wall_seconds','total_seconds','eval_seconds','prompt_eval_seconds','load_seconds')
def run(study,output,verify=False):
    study=Path(study).resolve();output=safe_output(output)
    require(study!=output and study not in output.parents and output not in study.parents,'Study and output overlap')
    verify_data()
    def load(name):return json.loads((study/name).read_text())
    def rows(name):
        with gzip.open(study/name,'rt',encoding='utf-8') as stream:return [json.loads(s) for s in stream if s.strip()]
    for name,expected in load('data/SHA256SUMS.json').items():
        path=(study/name).resolve();require(study in path.parents,'Checksum path escapes study')
        require(hashlib.sha256(path.read_bytes()).hexdigest()==expected,'Study evidence checksum differs: '+name)
    provenance=load('provenance/run.json');require(provenance['post_study_replacement'] and provenance['scientific_comparison_valid'] is False,'Supplement expects descriptive follow-up')
    old_rows=read_rows('data/calls.jsonl.gz');new_rows=rows('data/calls.jsonl.gz')
    original={r['response']['request_hash']:r for r in old_rows if r['verdict']['kind']!='request_error'}
    require(len(original)==sum(r['verdict']['kind']!='request_error' for r in old_rows),'Duplicate original request identity')
    retained={r['model'] for r in old_rows}&{r['model'] for r in new_rows}
    expected=[]
    for row in new_rows:
        if row['model'] not in retained:continue
        identity=row['response']['request_hash'];parent=original.get(identity)
        if parent:require(parent['model']==row['model'],'Matched identity changes model')
        def textsha(r):return hashlib.sha256(r['response']['text'].encode()).hexdigest()
        expected.append(dict(model=row['model'],request_kind='independent' if '/ind/' in row['uid'] else 'feedback',new_uid=row['uid'],old_uid=parent['uid'] if parent else None,request_identity_sha256=identity,matched_original_identity=parent is not None,full_payload_equality_checked_in_archive=True if parent else None,old_text_sha256=textsha(parent) if parent else None,new_text_sha256=textsha(row),old_accepted=bool(parent['verdict']['accepted']) if parent else None,new_accepted=bool(row['verdict']['accepted'])))
    require(rows('data/repeatability_ledger.jsonl.gz')==expected,'Repeatability witness ledger differs from supplied raw responses')
    repeatability=[]
    for model in sorted(retained):
        for kind in ['independent','feedback']:
            group=[r for r in expected if r['model']==model and r['request_kind']==kind];matched=[r for r in group if r['matched_original_identity']]
            repeatability.append(dict(model=model,request_kind=kind,new_requests_in_kind=len(group),exact_identity_matches=len(matched),text_equal=sum(r['old_text_sha256']==r['new_text_sha256'] for r in matched),acceptance_equal=sum(r['old_accepted']==r['new_accepted'] for r in matched),both_correct=sum(r['old_accepted'] and r['new_accepted'] for r in matched),old_only_correct=sum(r['old_accepted'] and not r['new_accepted'] for r in matched),new_only_correct=sum(not r['old_accepted'] and r['new_accepted'] for r in matched),both_incorrect=sum(not r['old_accepted'] and not r['new_accepted'] for r in matched)))
    usage={}
    for field in COSTS:
        values=[r['response'].get(field) for r in new_rows];observed=[v for v in values if isinstance(v,(int,float))]
        usage[field]={'sum_observed':sum(observed),'missing_calls':len(values)-len(observed)}
    with gzip.open(study/'data/portfolios.json.gz','rt',encoding='utf-8') as stream:portfolios=json.load(stream)
    family_totals=[]
    for family in sorted({r['family'] for r in portfolios}):
        for method in sorted({r['method'] for r in portfolios}):
            rr=[r for r in portfolios if r['family']==family and r['method']==method]
            family_totals.append(dict(family=family,method=method,n=len(rr),solved=sum(r['accepted'] for r in rr)))
    if verify:
        sort_repeat=lambda values:sorted(values,key=lambda r:(r['model'],r['request_kind']))
        require(sort_repeat(repeatability)==sort_repeat(load('results/reference/repeatability_summary.json')['rows']),'Reference repeatability differs')
        reference=load('results/reference/physical_usage.json')
        require(set(usage)==set(reference),'Cost fields differ')
        for field,values in usage.items():
            require(values['missing_calls']==reference[field]['missing_calls'] and math.isclose(values['sum_observed'],reference[field]['sum_observed'],rel_tol=1e-12,abs_tol=1e-12),'Reference physical usage differs: '+field)
        sort_family=lambda values:sorted(values,key=lambda r:(r['family'],r['method']))
        require(sort_family(family_totals)==sort_family(load('results/reference/family_totals.json')),'Reference family totals differ')
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/'physical_usage.json',usage);write_json(output/'repeatability_summary.json',{'scope':load('provenance/supplement_scope.json'),'rows':repeatability});write_json(output/'family_totals.json',family_totals)
    status={'status':'passed','retained_configuration_calls':len(expected),'matched_identity_pairs':sum(r['matched_original_identity'] for r in expected),'cost_rows_recomputed':len(new_rows),'reference_tables_checked':verify,'new_model_inference':False,'full_request_payloads_rechecked_here':False,'scope':'Post hoc descriptive supplement. Full payload equality was checked separately in the original archives; portable evidence rechecks matching request hashes and outcomes.'}
    write_json(output/'SUPPLEMENT_STATUS.json',status);return status
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();print(run(a.study,a.output,a.verify))
