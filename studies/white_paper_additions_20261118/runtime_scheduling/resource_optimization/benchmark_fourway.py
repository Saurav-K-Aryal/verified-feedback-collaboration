#!/usr/bin/env python3
"""Operational 1+1 versus 2+2 benchmark on a controller-owned isolated server.

This helper never starts, stops, or reconfigures either Ollama server. The caller
owns server cleanup, power suspension, and absolute deadlines. No science runs.
"""
from __future__ import annotations
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import threading
import time
import urllib.request

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
PLAN=HERE/'FOURWAY_BENCHMARK_PLAN.json'
OUT=HERE/'concurrency_fourway'
ENDPOINT='http://127.0.0.1:11535'
MODELS=['mistral-small3.2:24b','phi4:14b']
MODES=['serial','one_per_model','two_per_model']
ENV={'OLLAMA_HOST':'127.0.0.1:11535','OLLAMA_NUM_PARALLEL':'2','OLLAMA_MAX_LOADED_MODELS':'2','OLLAMA_CONTEXT_LENGTH':'8192'}
MODE_ORDER=[['serial','one_per_model','two_per_model'],['one_per_model','two_per_model','serial'],
            ['two_per_model','serial','one_per_model'],['two_per_model','one_per_model','serial']]
ARTIFACTS=['EXECUTION_END.json','ANALYSIS.json','reach_by_depth.csv','reach_by_depth.pdf','RESULTS.md','PASTE_READY.txt']

def now():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def require(value,message):
    if not value:raise RuntimeError(message)
def identity(pid):
    p=subprocess.run(['ps','-p',str(pid),'-o','lstart=','-o','command='],capture_output=True,text=True,timeout=5)
    return ' '.join(p.stdout.strip().split()) if p.returncode==0 and p.stdout.strip() else None
def api(endpoint,route,payload=None,timeout=10):
    data=None if payload is None else json.dumps(payload).encode()
    request=urllib.request.Request(endpoint+'/api/'+route,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)
def telemetry():
    memory=subprocess.run(['memory_pressure','-Q'],capture_output=True,text=True,timeout=5)
    match=re.search(r'System-wide memory free percentage:\s*(\d+)%',memory.stdout)
    power=subprocess.run(['pmset','-g','batt'],capture_output=True,text=True,timeout=5)
    return {'utc':now(),'memory_free_percent':int(match.group(1)) if match else None,
            'external_power':power.returncode==0 and 'AC Power' in power.stdout}
def prompt(block,slot):
    return ('This is a synthetic timing exercise, not a research evaluation. A fictional workshop sorts wooden '
            'tokens into bins. Each token has a printed number, a painted color, and a shape. No real people, '
            'private records, or source documents are involved. Produce a long numbered list of independent '
            'inventory entries in plain text. Each entry should state the token number, color, shape, and bin. '
            'Cycle colors red, blue, green, yellow and shapes circle, square, triangle. Start at token '
            f'{100*block+20*slot+1}. Continue making entries for at least 100 tokens. Do not summarize or stop early. '
            'Begin the numbered list immediately and do not add an introduction.')
def verify_plan():
    plan=read(PLAN)
    require(sha(__file__)==plan['code_sha256'],'Four-way benchmark source changed')
    require(sha(plan['binary_path'])==plan['binary_sha256'],'Ollama binary changed')
    return plan
def verify_primary():
    primary=read(BASE/'continuation/ORCHESTRATION_PLAN.json')['primary']
    require(identity(primary['pid'])!=primary['identity'],'Original Gemma primary is still running')
    folder=BASE/'topic3/T3A_gemma'
    require(all((folder/name).is_file() and (folder/name).stat().st_size>0 for name in ARTIFACTS),'Primary artifact set is incomplete')
    result=read(folder/'ANALYSIS.json')
    require(result.get('complete') is True and result['protocol_sha256']==sha(folder/'TEST_PROTOCOL.json'),'Primary is incomplete or protocol differs')

def verify_server(receipt_path,endpoint,plan):
    require(endpoint==ENDPOINT,'Only the approved loopback endpoint is permitted')
    receipt=read(receipt_path)
    require(receipt.get('controller_owned') is True and receipt.get('stage')=='isolated_server','Server is not controller-owned infrastructure')
    require(receipt.get('endpoint')==ENDPOINT,'Receipt endpoint differs')
    require(receipt.get('command')==[plan['binary_path'],'serve'],'Server binary command differs')
    require(receipt.get('binary_sha256')==plan['binary_sha256'],'Server binary receipt differs')
    require(all(receipt.get('environment',{}).get(k)==v for k,v in ENV.items()),'Server parallel configuration differs')
    pid=receipt['pid'];require(receipt.get('identity') and identity(pid)==receipt['identity'],'Server PID identity is not verified')
    require(os.getpgid(pid)==receipt['pgid']==pid,'Isolated server does not own its process group')
    listener=subprocess.run(['lsof','-nP','-iTCP:11535','-sTCP:LISTEN','-F','p'],capture_output=True,text=True,timeout=5)
    pids={int(line[1:]) for line in listener.stdout.splitlines() if line.startswith('p') and line[1:].isdigit()}
    require(listener.returncode==0 and pids=={pid},'Port listener is not exclusively the verified owned server')
    version=api(endpoint,'version');require(version==plan['server_version'],'Isolated server version differs')
    tags={model['name']:model for model in api(endpoint,'tags')['models'] if model['name'] in MODELS}
    require(tags==plan['model_metadata'],'Isolated server model metadata differs from the frozen shared-server metadata')
    state_path=receipt_path.parent/'STATE.json'
    if state_path.exists():
        state=read(state_path)
        for name,stage in state.get('stages',{}).items():
            process=stage.get('process',{})
            if name in ['isolated_server','free_gpu_benchmark','fourway_benchmark'] or process.get('pid')==os.getpid():continue
            if stage.get('status') in ['running','launching','ambiguous_live'] and process.get('pid') and identity(process['pid']):
                raise RuntimeError('A scientific stage remains active: '+name)
    processes=subprocess.run(['ps','-axo','pid=,command='],capture_output=True,text=True,timeout=5)
    require(processes.returncode==0,'Cannot inspect scientific processes')
    for line in processes.stdout.splitlines():
        if str(os.getpid())==line.strip().split(' ',1)[0]:continue
        if ('t3a_bridge.py' in line and any(f' {v} ' in line+' ' for v in ['test','replicate','develop','run'])) or ('optional_phi.py' in line and any(f' {v} ' in line+' ' for v in ['generate','score'])) or ('length_optional/run_length.py' in line and ' run' in line):
            raise RuntimeError('A scientific generation or scoring process remains active')
    old_resident={m['name'] for m in api('http://127.0.0.1:11434','ps')['models']}
    require(not old_resident.intersection(MODELS+['gemma4:12b']),'Study models remain on shared server; caller must drain/unload them before isolated benchmarking')
    return receipt

def verify_runner_capacity(receipt_path,endpoint):
    """Check actual backend slots/context, not merely requested environment."""
    receipt=read(receipt_path)
    require(identity(receipt['pid'])==receipt['identity'],'Owned server changed before capacity verification')
    processes=subprocess.run(['ps','-axo','pid=,pgid=,command='],capture_output=True,text=True,timeout=5)
    require(processes.returncode==0,'Cannot inspect isolated backend runners')
    result=[]
    for line in processes.stdout.splitlines():
        fields=line.strip().split(None,2)
        if len(fields)!=3 or not fields[0].isdigit() or not fields[1].isdigit() or int(fields[1])!=receipt['pgid']:continue
        command=shlex.split(fields[2])
        if not command or Path(command[0]).name!='llama-server':continue
        require('--host' in command and command[command.index('--host')+1]=='127.0.0.1','Backend runner is not loopback-bound')
        require('--port' in command,'Backend runner port is unavailable')
        port=int(command[command.index('--port')+1]);require(0<port<65536,'Invalid backend port')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/props',timeout=10) as response:props=json.load(response)
        slots=props.get('total_slots');context=props.get('default_generation_settings',{}).get('n_ctx')
        require(slots==2 and context==8192,'Actual backend slots/context differ from two workers with 8192 tokens per slot')
        pid=int(fields[0]);require(os.getpgid(pid)==receipt['pgid'],'Backend runner ownership changed')
        result.append({'pid':pid,'identity_sha256':hashlib.sha256((identity(pid) or '').encode()).hexdigest(),
                       'port':port,'total_slots':slots,'context_per_slot':context})
    require(len(result)==2,'Expected exactly two controller-owned model runners')
    resident=api(endpoint,'ps')['models']
    require({model['name'] for model in resident}==set(MODELS),'Unexpected isolated resident model set')
    return {'verified_utc':now(),'runners':result,'actual_two_slots_per_model_verified':True,
            'ollama_context_metadata':{model['name']:model.get('context_length') for model in resident},
            'context_authority':'Each backend runner reports n_ctx8192 and two slots. Ollama aggregate context metadata is recorded without assuming per-slot semantics.'}

def select_mode(phases,calls,memory_ok):
    table={(row['block'],row['mode']):row for row in phases}
    complete=all((block,mode) in table for block in range(4) for mode in MODES)
    timed=[row for row in calls if row['mode']!='warmup']
    errors=sum(bool(row.get('error')) for row in calls)
    identical=complete and len(timed)==48
    if identical:
        for block in range(4):
            for model in MODELS:
                for slot in range(2):
                    values=[next((row.get('output_tokens') for row in timed if row['block']==block and row['model']==model and row['slot']==slot and row['mode']==mode),None) for mode in MODES]
                    if len(set(values))!=1 or values[0]!=128:identical=False
    comparisons={}
    if complete:
        for faster,reference in [('one_per_model','serial'),('two_per_model','one_per_model'),('two_per_model','serial')]:
            gains=[1-table[block,faster]['wall_seconds']/table[block,reference]['wall_seconds'] for block in range(4)]
            median=statistics.median(gains);wins=sum(gain>0 for gain in gains)
            comparisons[faster+'_vs_'+reference]={'fractional_wall_improvement':gains,'median':median,'faster_blocks':wins,'performance_gate':median>=.10 and wins>=3}
    valid=complete and errors==0 and identical and memory_ok
    selected='serial'
    if valid:
        if comparisons['two_per_model_vs_one_per_model']['performance_gate'] and comparisons['two_per_model_vs_serial']['performance_gate']:selected='two_per_model'
        elif comparisons['one_per_model_vs_serial']['performance_gate']:selected='one_per_model'
    return {'selected_mode':selected,'comparisons':comparisons,'complete_blocks':sum(all((block,mode) in table for mode in MODES) for block in range(4)),
            'errors':errors,'identical_output_tokens':identical,'memory_power_guard_passed':memory_ok,'valid_comparison':valid,
            'supervisor_exit_code':0 if valid else 2}

class Benchmark:
    def __init__(self,plan,receipt_path,endpoint):
        self.plan=plan;self.receipt_path=receipt_path;self.endpoint=endpoint
        self.lock=threading.RLock();self.stop=threading.Event();self.abort=threading.Event()
        self.calls=[];self.phases=[];self.samples=[];self.reason=None
        self.start=time.monotonic();self.deadline=self.start+plan['max_wall_seconds']
        self.hard=datetime.fromisoformat(plan['hard_stop_utc']).timestamp()
    def append(self,name,row):
        with self.lock:
            with (OUT/name).open('a') as stream:stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush()
    def guard_sample(self):
        try:
            sample=telemetry();okay=sample['external_power'] and sample['memory_free_percent'] is not None and sample['memory_free_percent']>=20
        except Exception as error:sample={'utc':now(),'error':repr(error)};okay=False
        with self.lock:self.samples.append(sample)
        self.append('TELEMETRY.jsonl',sample)
        if not okay:self.reason='Power or memory guard failed';self.abort.set()
        if time.monotonic()>=self.deadline or time.time()>=self.hard:self.reason='Frozen runtime deadline reached';self.abort.set()
    def monitor(self):
        while not self.stop.is_set():self.guard_sample();self.stop.wait(2)
    def request(self,block,mode,model,slot):
        if self.abort.is_set():raise RuntimeError(self.reason or 'Operational guard halted benchmark')
        remaining=min(self.deadline-time.monotonic(),self.hard-time.time())
        require(remaining>1,'Frozen runtime deadline reached before request')
        seed=202611190000+max(0,block+1)*100+MODELS.index(model)*10+slot
        payload={'model':model,'prompt':prompt(block,slot),'stream':False,'keep_alive':'18h',
                 'options':{'num_ctx':8192,'num_predict':128,'seed':seed,'temperature':.7,'top_p':.9,'repeat_penalty':1.0}}
        row={'id':f'{mode}-{block}-{MODELS.index(model)}-{slot}','model':model,'block':block,'mode':mode,'slot':slot,'seed':seed,'started_utc':now()}
        self.append('REQUESTS.jsonl',row);beg=time.monotonic()
        try:
            response=api(self.endpoint,'generate',payload,timeout=min(90,remaining));text=response.get('response','')
            row.update(done=response.get('done'),done_reason=response.get('done_reason'),output_tokens=response.get('eval_count'),
                       prompt_tokens=response.get('prompt_eval_count'),response_sha256=hashlib.sha256(text.encode()).hexdigest(),
                       response_characters=len(text),load_seconds=response.get('load_duration',0)/1e9,
                       eval_seconds=response.get('eval_duration',0)/1e9,error=None)
            if row['done'] is not True or not text.strip() or not isinstance(row['output_tokens'],int) or row['output_tokens']<=0:row['error']='Incomplete, empty or missing token-count response'
        except Exception as error:row.update(error=f'{type(error).__name__}: {error}',output_tokens=None)
        row.update(wall_seconds=time.monotonic()-beg,finished_utc=now())
        with self.lock:self.calls.append(row)
        self.append('CALLS.jsonl',row)
        if row['error']:self.reason='Request error; unknown outstanding server work is possible';self.abort.set()
        return row
    def sequence(self,block,mode,model):return [self.request(block,mode,model,slot) for slot in range(2)]
    def phase(self,block,mode):
        require(not self.abort.is_set(),self.reason or 'Operational guard failed')
        started=time.monotonic();calls=[]
        if mode=='serial':
            order=MODELS if block%2==0 else MODELS[::-1]
            for slot in range(2):
                for model in order:calls.append(self.request(block,mode,model,slot))
        elif mode=='one_per_model':
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(self.sequence,block,mode,model) for model in MODELS]
                for future in futures:calls.extend(future.result())
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures=[pool.submit(self.request,block,mode,model,slot) for slot in range(2) for model in MODELS]
                calls=[future.result() for future in futures]
        row={'block':block,'mode':mode,'wall_seconds':time.monotonic()-started,'output_tokens':sum(c['output_tokens'] or 0 for c in calls),
             'errors':sum(bool(c['error']) for c in calls),'finished_utc':now()}
        self.phases.append(row);self.append('PHASES.jsonl',row);print(json.dumps(row),flush=True)
    def run(self):
        telemetry_thread=threading.Thread(target=self.monitor,daemon=True);telemetry_thread.start()
        try:
            self.guard_sample()
            require(not self.abort.is_set(),self.reason or 'Startup guard failed')
            for model in MODELS:self.request(-1,'warmup',model,0)
            save(OUT/'RUNNER_CAPACITY.json',verify_runner_capacity(self.receipt_path,self.endpoint))
            for block in range(4):
                for mode in MODE_ORDER[block]:self.phase(block,mode)
        except Exception as error:self.reason=self.reason or repr(error);self.abort.set()
        finally:self.stop.set();telemetry_thread.join(timeout=12)
        safe=bool(self.samples) and all(row.get('external_power') is True and row.get('memory_free_percent') is not None and row['memory_free_percent']>=20 for row in self.samples)
        result=select_mode(self.phases,self.calls,safe)
        if self.abort.is_set():result['supervisor_exit_code']=2;result['selected_mode']='serial';result['valid_comparison']=False
        result.update(finished_utc=now(),elapsed_seconds=time.monotonic()-self.start,halt_reason=self.reason,
                      minimum_memory_free_percent=min((row['memory_free_percent'] for row in self.samples if row.get('memory_free_percent') is not None),default=None),
                      timed_calls=sum(row['mode']!='warmup' for row in self.calls),server_receipt_sha256=sha(self.receipt_path),
                      plan_sha256=sha(PLAN),protocol_sha256=sha(OUT/'PROTOCOL.json'),code_sha256=sha(__file__),
                      endpoint=self.endpoint,server_left_running_under_controller_ownership=True,
                      condition='After complete primary exit, before scientific timing, on the same isolated two-slot server in every mode. Synthetic fixed-length timing only; no scientific outcomes.',
                      cleanup_contract='Caller must stop its isolated server and halt on nonzero exit. A zero exit transfers no ownership because the caller already owns the server. Before detector scoring, drain/unload all owned models, verify no resident models, and stop the owned server.')
        save(OUT/'RESULT.json',result);print(json.dumps(result),flush=True)
        return result['supervisor_exit_code']

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['check','run'])
    parser.add_argument('--authorize-run',action='store_true');parser.add_argument('--server-receipt',type=Path)
    parser.add_argument('--endpoint',default=ENDPOINT);args=parser.parse_args()
    plan=verify_plan()
    if args.phase=='check':print(json.dumps({'status':'prepared, no requests made','code_sha256':plan['code_sha256'],'plan_sha256':sha(PLAN),'endpoint':ENDPOINT}));return 0
    require(args.authorize_run and args.server_receipt,'Controller review and owned-server receipt are required')
    verify_primary();receipt=verify_server(args.server_receipt,args.endpoint,plan)
    require(time.time()+plan['max_wall_seconds']+120<datetime.fromisoformat(plan['hard_stop_utc']).timestamp(),'Insufficient time before global stop')
    OUT.mkdir(exist_ok=False)
    protocol=dict(plan);protocol.update(frozen_utc=now(),phase='after_primary_four_request_comparison',server_receipt_sha256=sha(args.server_receipt),
        verified_server_pid=receipt['pid'],verified_server_identity=receipt['identity'],plan_sha256=sha(PLAN),
        no_scientific_inputs=True,no_generated_text_saved=True,ownership='Server remains owned by the calling controller')
    save(OUT/'PROTOCOL.json',protocol)
    return Benchmark(plan,args.server_receipt,args.endpoint).run()
if __name__=='__main__':raise SystemExit(main())
