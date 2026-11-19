#!/usr/bin/env python3
"""Versioned operational amendment: benchmark-gated overlap of distinct models.

No launch is performed by prepare/check. Frozen scientific scripts are reused.
The original controller's lock excludes simultaneous cross-version controllers.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import run_remaining as b

ORIGINAL_CONTROL=b.CONTROL
CONTROL=b.HERE/'continuation_v2'
RESOURCE=b.HERE/'resource_optimization'
BENCHMARK=RESOURCE/'concurrency_fourway'
SERVER_RECEIPT=CONTROL/'ISOLATED_SERVER.json'
ENDPOINT='http://127.0.0.1:11535'
OLLAMA=Path('/Applications/Ollama.app/Contents/Resources/ollama')
SERVER_ENV={'OLLAMA_HOST':'127.0.0.1:11535','OLLAMA_NUM_PARALLEL':'2',
            'OLLAMA_MAX_LOADED_MODELS':'2','OLLAMA_CONTEXT_LENGTH':'8192'}
SCRIPT=Path(__file__).resolve()
b.CONTROL=CONTROL;b.PLAN=CONTROL/'ORCHESTRATION_PLAN.json';b.STATE=CONTROL/'STATE.json'


def require_serial_inactive():
    old=b.read(ORIGINAL_CONTROL/'STATE.json',{})
    pid=old.get('controller_pid')
    if pid and b.process_exists(pid):
        b.require(b.process_identity(pid)!=old.get('controller_identity'),
                  'Original serial controller remains active; root must perform the reviewed handover first')
    for prior in old.get('stages',{}).values():
        record=prior.get('process')
        b.require(not record or not b.process_exists(record['pid']),
                  'Original controller has an unresolved live child; refuse cross-version work')
        b.require(prior.get('status')!='launching','Original controller has an unresolved launch')


def process_group_members(pgid):
    reply=subprocess.run(['ps','-axo','pid=,pgid='],capture_output=True,text=True,timeout=10)
    b.require(reply.returncode==0,'Cannot verify isolated process-group exit')
    members=[]
    for line in reply.stdout.splitlines():
        fields=line.split()
        if len(fields)==2 and int(fields[1])==pgid:members.append(int(fields[0]))
    return members


def isolated_listener_exists():
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(('127.0.0.1',11535))==0


def benchmark_complete(result):
    return bool(result and result.get('supervisor_exit_code')==0
                and result.get('complete_blocks')==4 and result.get('errors')==0
                and result.get('selected_mode') in ['serial','one_per_model','two_per_model'])


def overlap_ready(folder=b.MISTRAL):
    """Completed first test request proves standalone timing and sample freeze ended."""
    return (folder/'TEST_PROTOCOL.json').is_file() and b.line_counts(folder/'test_calls.jsonl',True)['recorded']>0


class ControllerV2(b.Controller):
    def __init__(self,plan):
        super().__init__(plan)
        self.parallel={}
        self.parallel_progress_time=0.
        self.server=None;self.server_process=None
        self.workers=1;self.mode='serial'

    def power(self):
        powered=super().power()
        if not powered and self.current and self.current.get('stage')=='free_gpu_benchmark':
            if not self.state.get('benchmark_interrupted_by_power'):
                self.state['benchmark_interrupted_by_power']=True;self.persist()
                b.event('benchmark_invalidated_by_power_pause')
        if self.server:
            b.require(b.owned_process(self.server),'Isolated server identity is no longer verified; halt all new work')
            if not powered and not self.server.get('paused'):
                b.signal_owned(self.server,signal.SIGSTOP);self.server['paused']=True;self.persist_server()
            elif powered and self.server.get('paused'):
                b.signal_owned(self.server,signal.SIGCONT);self.server['paused']=False;self.persist_server()
        return powered

    def persist_server(self,new_receipt=False):
        self.state['infrastructure']={'isolated_server':self.server};self.persist()
        if new_receipt:
            # The benchmark pins this exact launch receipt. Power and shutdown
            # state belong in STATE, never mutate the referenced launch record.
            b.write(SERVER_RECEIPT,self.server)
            archive=CONTROL/'server_receipts'/(b.sha(SERVER_RECEIPT)+'.json')
            if not archive.exists():b.write(archive,self.server)

    def start_server(self):
        prior=b.read(SERVER_RECEIPT,{})
        b.require(prior.get('status')!='launching','Interrupted isolated-server launch requires process review')
        if prior.get('pid') and b.process_exists(prior['pid']):
            b.require(b.owned_process(prior),'Prior isolated server has an ambiguous live identity')
            self.server=prior;self.persist_server();return
        b.require(not self.parallel,'Cannot start a replacement server while generation clients survive')
        # Do not bind over an unowned listener or silently reuse another server.
        b.require(not isolated_listener_exists(),'Isolated port already has an unowned listener')
        if not self.wait_power():raise RuntimeError('Deadline before isolated server start')
        b.require(not self.past_deadline(),'Deadline before isolated server spawn')
        env=os.environ.copy();env.update(SERVER_ENV)
        command=[str(OLLAMA),'serve'];path=CONTROL/'isolated_server.log'
        b.write(SERVER_RECEIPT,{'status':'launching','command':command,'started_utc':b.now()})
        with path.open('ab',buffering=0) as stream:
            process=subprocess.Popen(command,cwd=b.ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                     start_new_session=True,close_fds=True)
        self.server_process=process;identity=None
        for _ in range(20):
            identity=b.process_identity(process.pid)
            if identity or process.poll() is not None:break
            time.sleep(.05)
        self.server={'stage':'isolated_server','status':'running','pid':process.pid,'pgid':process.pid,
                     'identity':identity,'controller_owned':True,'command':command,'started_utc':b.now(),
                     'started_epoch':time.time(),'endpoint':ENDPOINT,'environment':SERVER_ENV,
                     'binary_sha256':b.sha(OLLAMA),'paused':False,'log':str(path)}
        self.persist_server(new_receipt=True);b.event('isolated_server_started',pid=process.pid,endpoint=ENDPOINT)
        until=min(self.hard,time.time()+60)
        while time.time()<until and not self.shutdown:
            b.require(b.owned_process(self.server),'Isolated server exited or identity is ambiguous')
            try:
                with b.urllib.request.urlopen(ENDPOINT+'/api/version',timeout=2) as response:
                    version=json.loads(response.read()).get('version')
                if version:
                    b.event('isolated_server_api_ready',version=version);return
            except Exception:pass
            time.sleep(1)
        raise RuntimeError('Isolated server API did not become ready')

    def wait_server_quiescence(self,pgid):
        # A runner can outlive the server parent briefly during normal shutdown.
        # Observe only: never signal a group whose original leader has exited.
        until=time.monotonic()+min(15,max(0,self.hard-time.time()))
        while True:
            members=process_group_members(pgid);listening=isolated_listener_exists()
            if not members and not listening:return True
            remaining=until-time.monotonic()
            if remaining<=0:return False
            time.sleep(min(.2,remaining))

    def stop_server(self,reason):
        if not self.server:return
        record=self.server
        if b.owned_process(record):self.stop_owned(record,reason)
        if self.server_process is not None:
            try:self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
        b.require(not b.process_exists(record['pid']),'Isolated server remains alive or ambiguous; no detector work permitted')
        b.require(self.wait_server_quiescence(record['pgid']),
                  'Isolated runner group or listener survives the cleanup window; no detector work permitted')
        record['status']='stopped';record['finished_utc']=b.now();self.persist_server()
        b.event('isolated_server_stopped',pid=record['pid'],reason=reason)
        self.server=None;self.server_process=None

    def ready(self,stage):
        if stage=='free_gpu_benchmark':return (not self.state.get('benchmark_interrupted_by_power') and benchmark_complete(b.read(BENCHMARK/'RESULT.json')))
        return super().ready(stage)

    def persist_parallel(self):
        self.state['parallel_active']=list(self.parallel)
        self.persist()

    def start_async(self,name,command,deadline):
        """Spawn/adopt one generation client; only the supervisor mutates state."""
        prior=self.state['stages'].get(name,{})
        b.require(prior.get('status')!='launching' or prior.get('process'),
                  'Interrupted launch lacks an identity; manual review is required')
        old=prior.get('process')
        if old and b.process_exists(old['pid']):
            b.require(b.owned_process(old),'Unverified live generation client; refusing further launches')
            self.parallel[name]=(old,None);self.persist_parallel()
            b.event('adopting_owned_stage',stage=name,pid=old['pid']);return True
        if self.ready(name):
            self.state['stages'][name]={'status':'complete_existing_artifacts','finished_utc':b.now()}
            self.persist();return False
        limit=min(self.hard,deadline)
        if self.past_deadline() or time.time()>=limit:return False
        # While a sibling is active, never block inside wait_power: the shared
        # monitor must remain free to pause that sibling and enforce deadlines.
        if self.parallel:
            if not self.power():return None
        elif not self.wait_power():return False
        if self.past_deadline() or time.time()>=limit:return False
        attempt=prior.get('attempts',0)+1;path=CONTROL/(name+f'.attempt{attempt}.log')
        env=os.environ.copy();env['PYTHONUNBUFFERED']='1'
        self.state['stages'][name]={'status':'launching','attempts':attempt,'command':command,'started_epoch':time.time()}
        self.persist()
        try:
            with path.open('ab',buffering=0) as stream:
                process=subprocess.Popen(command,cwd=b.ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                         start_new_session=True,close_fds=True)
        except Exception as error:
            self.state['stages'][name].update(status='launch_failed',error=repr(error));self.persist();raise
        identity=None
        for _ in range(10):
            identity=b.process_identity(process.pid)
            if identity or process.poll() is not None:break
            time.sleep(.05)
        record={'stage':name,'pid':process.pid,'pgid':process.pid,'identity':identity,
                'controller_owned':True,'command':command,'started_utc':b.now(),'started_epoch':time.time(),
                'stage_deadline_epoch':limit,'paused':False,'log':str(path)}
        self.parallel[name]=(record,process)
        self.state['stages'][name]={'status':'running','attempts':attempt,'process':record}
        self.persist_parallel();b.event('stage_started',stage=name,pid=process.pid,command=command,log=str(path))
        return True

    def tick_parallel(self):
        """One pass: verify all identities before any new launches or GPU work."""
        for name,(record,process) in list(self.parallel.items()):
            code=process.poll() if process is not None else None
            exited=process is not None and code is not None
            if not exited and not b.owned_process(record):
                if b.process_exists(record['pid']):
                    self.state['stages'][name]['status']='ambiguous_live';self.persist_parallel()
                    b.event('ambiguous_live_process',stage=name,pid=record['pid'])
                    raise RuntimeError('Live child identity is ambiguous; no further GPU work is permitted')
                exited=True
            if exited:
                success=(code==0 or code is None) and self.ready(name)
                self.state['stages'][name].update(status='complete' if success else 'incomplete_or_failed',
                                                 exit_code=code,finished_utc=b.now())
                del self.parallel[name];self.persist_parallel()
                self.log_progress(name,True)
                b.event('stage_finished',stage=name,status=self.state['stages'][name]['status'],exit_code=code)
        if not self.parallel:return
        if self.past_deadline():
            self.stop_parallel('global deadline or controller shutdown')
            return
        powered=self.power()
        for name,(record,process) in list(self.parallel.items()):
            if self.past_deadline() or time.time()>=record['stage_deadline_epoch']:
                self.stop_owned(record,'global/stage deadline or controller shutdown')
                if process is not None:
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:pass
                # Keep the record until exit is verified on the next tick.
                continue
            if not powered and not record.get('paused'):
                b.signal_owned(record,signal.SIGSTOP);record['paused']=True;self.persist_parallel()
            elif powered and record.get('paused'):
                b.signal_owned(record,signal.SIGCONT);record['paused']=False;self.persist_parallel()
        if time.monotonic()-self.parallel_progress_time>=60:
            for name in self.parallel:self.log_progress(name,True)
            self.parallel_progress_time=time.monotonic()

    def stop_parallel(self,reason):
        # Notify all verified groups before waiting for any one child to exit.
        for record,process in list(self.parallel.values()):
            if b.owned_process(record):
                b.signal_owned(record,signal.SIGTERM);b.signal_owned(record,signal.SIGCONT)
        for record,process in list(self.parallel.values()):
            if b.owned_process(record):self.stop_owned(record,reason)
            if process is not None:
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:pass

    def reconcile(self):
        live=[name for name,prior in self.state['stages'].items()
              if prior.get('process') and b.process_exists(prior['process']['pid'])]
        b.require(not(set(live)&{'mistral','phi_generate'} and set(live)-{'mistral','phi_generate'}),
                  'A serial stage overlaps generation; manual process review is required')
        for name,prior in list(self.state['stages'].items()):
            record=prior.get('process')
            b.require(prior.get('status')!='launching' or record,
                      'Interrupted launch lacks a verified PID; manual review is required')
            if not record or not b.process_exists(record['pid']):continue
            b.require(b.owned_process(record),'A prior live child has an ambiguous identity')
            if name in ['mistral','phi_generate']:
                self.parallel[name]=(record,None)
            else:
                b.require(not self.parallel,'A serial GPU stage overlaps generation; manual review is required')
                self.current=record;code=self.monitor(record);self.current=None
                prior.update(status='complete_existing_artifacts' if self.ready(name) else 'incomplete_or_failed',
                             exit_code=code,finished_utc=b.now());self.persist()
        self.persist_parallel()

    def start_mistral(self):
        if 'mistral' in self.parallel or self.ready('mistral'):return
        existing=b.read(b.MISTRAL/'EXECUTION_START.json')
        allocation=b.replication_hours(time.time(),self.hard)
        if existing:
            remaining=existing['deadline_epoch']-time.time()
            allocation=remaining/3600 if remaining>=3600 else None
        if allocation is None or allocation<=0:
            self.state['stages']['mistral']={'status':'skipped_timing','finished_utc':b.now(),
                'reason':'less than one hour within the unchanged allocation rule'}
            self.persist();b.event('mistral_skipped_timing');return
        command=[str(b.PYTHON),str(RESOURCE/'dispatch_t3.py'),
                 '--workers',str(self.workers),'--base-url',ENDPOINT,'replicate','--authorize-run',
                 '--model','mistral-small3.2:24b','--replicate-from',str(b.REPLICATION),'--out',str(b.MISTRAL),
                 '--max-hours',str(allocation),'--hard-stop',self.plan['hard_stop_utc'],
                 '--max-n-per-depth',str(b.read(b.REPLICATION/'TEST_PROTOCOL.json')['test_n_per_depth'])]
        self.start_async('mistral',command,min(self.hard,time.time()+allocation*3600+120))

    def start_phi(self):
        budget=b.read(b.PHI/'PROTOCOL.json')['generation_budget_seconds']
        started=self.state['stages'].get('phi_generate',{}).get('process',{}).get('started_epoch',time.time())
        return self.start_async('phi_generate',[str(b.PYTHON),str(RESOURCE/'dispatch_phi.py'),'--authorize-run',
                         '--workers',str(self.workers),'--base-url',ENDPOINT,'--hard-stop',self.plan['hard_stop_utc']],
                         min(self.hard,started+budget+60))

    def generation_pair(self):
        # A surviving Phi client may follow an already failed/skipped Mistral.
        # Do not restart Mistral timing beside it during adoption.
        if not self.parallel:self.start_mistral()
        phi_attempted='phi_generate' in self.parallel or self.ready('phi_generate')
        while self.parallel or not phi_attempted:
            self.tick_parallel()
            if not phi_attempted and not self.past_deadline():
                if 'mistral' not in self.parallel or (self.mode!='serial' and overlap_ready()):
                    b.event('phi_generation_released',standalone_mistral_timing_finished=overlap_ready(),
                            mistral_still_active='mistral' in self.parallel)
                    phi_attempted=self.start_phi() is not None
            if self.past_deadline() and not self.parallel:break
            if self.parallel:time.sleep(5)
        b.require(not self.parallel,'Generation children remain active')

    def unload(self,model):
        if model in ['mistral-small3.2:24b','phi4:14b']:
            if not self.past_deadline():self.drain_generation_models([model])
        else:super().unload(model)

    def drain_generation_models(self,models=None,endpoint=ENDPOINT):
        # A client can exit while the server is finishing its last HTTP request.
        # Fail closed unless both unload requests succeed and neither model is
        # resident afterward. Never continue scoring after a swallowed timeout.
        b.require(not self.parallel,'Cannot drain with live generation clients')
        models=models or ['mistral-small3.2:24b','phi4:14b']
        for model in models:
            remaining=self.hard-time.time()
            b.require(remaining>2 and not self.shutdown,'Deadline/shutdown before model drain')
            request=b.urllib.request.Request(endpoint+'/api/generate',
                data=json.dumps({'model':model,'keep_alive':0}).encode(),
                headers={'Content-Type':'application/json'})
            with b.urllib.request.urlopen(request,timeout=min(120,remaining)) as response:
                result=json.loads(response.read())
            b.require(result.get('done') is True and not result.get('error'),
                      'Model unload was not confirmed; halt before detector scoring')
            b.event('generation_model_drain_requested',model=model)
        until=min(self.hard,time.time()+120)
        while time.time()<until and not self.shutdown:
            with b.urllib.request.urlopen(endpoint+'/api/ps',timeout=min(10,max(1,until-time.time()))) as response:
                resident=json.loads(response.read()).get('models')
            b.require(isinstance(resident,list),'Resident-model response unavailable')
            names={r.get('name',r.get('model')) for r in resident}
            if not names.intersection(models):
                b.event('generation_models_drained',models=models);return
            time.sleep(1)
        raise RuntimeError('Model drain remains uncertain; detector scoring is blocked')

    def post_generation(self):
        b.require(not self.parallel,'No scoring or finalization may overlap a generation client')
        if b.t3_ready(b.MISTRAL):self.finalize_t3(b.MISTRAL,'mistral')
        if self.past_deadline():return
        self.drain_generation_models()
        self.stop_server('generation complete and models drained')
        if self.past_deadline():return
        if self.ready('phi_generate'):
            scored=self.stage('phi_score',[str(b.PYTHON),str(b.HERE/'topic12/optional_phi.py'),'score','--ollama-slot'])
            if scored and not self.past_deadline():
                self.stage('phi_analyze',[str(b.PYTHON),str(b.HERE/'topic12/analyze_phi.py'),'analyze'])
        else:b.event('phi_scoring_skipped_without_complete_generation')
        if self.past_deadline():return
        command=[str(b.PYTHON),str(b.LENGTH/'run_length.py'),'run','--gpu-slot-authorized']
        if (b.LENGTH/'scores.jsonl').exists():command.append('--resume')
        self.stage('length',command)

    def run(self):
        require_serial_inactive()
        prior_server=b.read(SERVER_RECEIPT,{})
        if prior_server.get('pid') and b.process_exists(prior_server['pid']):
            b.require(b.owned_process(prior_server),'Prior isolated-server identity is ambiguous')
            self.server=prior_server
        self.reconcile()
        result=b.read(BENCHMARK/'RESULT.json')
        if self.parallel:
            b.require(self.server is not None and benchmark_complete(result),
                      'Cannot adopt generation clients without their server and a completed operational benchmark')
            self.mode=result['selected_mode'];self.workers=2 if self.mode=='two_per_model' else 1
            self.generation_pair();self.post_generation();return
        if self.past_deadline() or not self.wait_primary():return
        if not self.finalize_t3(b.GEMMA,'primary'):
            b.event('primary_finalization_failed_continuation_halted');return
        self.unload('gemma4:12b')
        self.start_server()
        # Release warm copies on the original service after the isolated API is
        # ready. Never stop or reconfigure the shared original Ollama service.
        self.drain_generation_models(models=['gemma4:12b','mistral-small3.2:24b','phi4:14b'],endpoint='http://127.0.0.1:11434')
        command=[str(b.PYTHON),'-B',str(RESOURCE/'benchmark_fourway.py'),'run','--authorize-run',
                 '--endpoint',ENDPOINT,'--server-receipt',str(SERVER_RECEIPT)]
        if not self.stage('free_gpu_benchmark',command,deadline=min(self.hard,time.time()+720)):
            raise RuntimeError('Operational benchmark was incomplete or failed; halt to avoid unknown in-flight requests')
        result=b.read(BENCHMARK/'RESULT.json')
        self.mode=result['selected_mode'];self.workers=2 if self.mode=='two_per_model' else 1
        self.state['scheduling_mode']=self.mode;self.state['workers_per_model']=self.workers
        self.persist();b.event('scheduling_gate_decision',mode=self.mode,workers_per_model=self.workers,
                               benchmark_result_sha256=b.sha(BENCHMARK/'RESULT.json'))
        self.generation_pair();self.post_generation()


def prepare():
    b.require(not b.PLAN.exists(),'V2 plan is already frozen; do not replace it')
    original=b.read(ORIGINAL_CONTROL/'ORCHESTRATION_PLAN.json')
    b.require(b.sha(ORIGINAL_CONTROL/'ORCHESTRATION_PLAN.json')==b.read(ORIGINAL_CONTROL/'PLAN_FREEZE.json')['plan_sha256'],
              'Original plan hash differs')
    for path,expected in original['input_sha256'].items():b.require(b.sha(path)==expected,'Original frozen dependency differs: '+path)
    dependencies=[SCRIPT,b.HERE/'test_run_remaining_v2.py',RESOURCE/'benchmark_fourway.py',
                  RESOURCE/'FOURWAY_BENCHMARK_PLAN.json',RESOURCE/'dispatch_t3.py',
                  RESOURCE/'test_dispatch_t3.py',RESOURCE/'dispatch_phi.py',RESOURCE/'PHI_DISPATCH_PLAN.json',
                  RESOURCE/'concurrency_benchmark/RESULT.json',RESOURCE/'concurrency_benchmark/PROTOCOL.json',
                  ORIGINAL_CONTROL/'ORCHESTRATION_PLAN.json',ORIGINAL_CONTROL/'PLAN_FREEZE.json',OLLAMA]
    plan=dict(original)
    plan.update(version='remaining-controller-2',prepared_utc=b.now(),controller_sha256=b.sha(SCRIPT),
                original_controller_plan_sha256=b.sha(ORIGINAL_CONTROL/'ORCHESTRATION_PLAN.json'))
    plan['input_sha256']={**original['input_sha256'],**{str(p):b.sha(p) for p in dependencies}}
    plan['stages']=['wait_primary','primary_finalize','free_gpu_benchmark','mistral','phi_generate',
                    'mistral_finalize','phi_score','phi_analyze','length']
    plan['operational_amendment']={
        'authorized_scope':'Explicit prospective override of the original serial-inference scheduling wording, limited to request ordering, isolated endpoint and benchmark-selected concurrency. Frozen source files are preserved, linked by hash below. Scientific tasks, prompts, decoding parameters, seeds, checkers and analyses are unchanged.',
        'decision':'Any observed controller power pause invalidates the performance comparison. After primary exit run the frozen four-way operational benchmark on an isolated server. Adopt serial, one_per_model or two_per_model only from the helper selected_mode field and its frozen paired wall-time, token-comparability, memory and zero-error gates. No scientific outcomes control mode selection.',
        'failed_gate':'A normally completed negative performance gate selects serial or one_per_model as specified by the frozen benchmark. Any failed/incomplete request benchmark halts and terminates the owned isolated server.',
        'selection_protection':'Mistral scientific timing and sample-size freeze run alone. Phi starts only after TEST_PROTOCOL.json and one completed Mistral test-call record, or after Mistral exits/skips.',
        'concurrency':'At most two generation clients and benchmark-selected one or two requests per model; never duplicate a whole experiment. Detector scoring and length wait until both clients exit, successful unload plus absent residency confirms model drain, and the owned isolated server exits.',
        'budgets':'Original Mistral/Phi wall-clock budget rules and absolute global deadline remain unchanged; power pauses do not extend deadlines.',
        'exclusion':'All versions hold the original continuation/controller.lock for their entire lifetime. V2 does not stop V1; root performs the reviewed wait-primary handover.',
        'safety':'Each generation child has a separate session, exact creation-time/command identity and persistent record. Any ambiguous live identity halts further work. Cleanup visits every owned child, not only the inherited current field.',
        'statistics':'Scheduling decisions use only operational timing, errors, output-token counts and memory. No scientific outcomes are consulted.',
        'isolated_server':{'binary':str(OLLAMA),'binary_sha256':b.sha(OLLAMA),'endpoint':ENDPOINT,'environment':SERVER_ENV,
                           'ownership':'Separate controller-owned process group, paused with children on battery and terminated on cleanup or absolute deadline. Original shared server is never signaled or reconfigured.'}}
    plan['serial_rule']='This prospective operational amendment overrides the previous serial-request rule only for the measured Mistral/Phi dispatchers. Original global controller lock, exact scientific input hashes and all other serial GPU stages remain mandatory.'
    b.write(b.PLAN,plan)
    b.write(CONTROL/'PLAN_FREEZE.json',{'prepared_utc':b.now(),'plan_sha256':b.sha(b.PLAN),'controller_sha256':b.sha(SCRIPT)})
    print(str(b.PLAN))


def run_controller(args):
    b.require(args.authorize_launch,'Root review and --authorize-launch are required')
    plan=b.verify_plan();CONTROL.mkdir(parents=True,exist_ok=True)
    with (ORIGINAL_CONTROL/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_serial_inactive();c=ControllerV2(plan)
        def stop(signum,frame):
            c.shutdown=True;b.event('controller_shutdown_requested',signal=signal.Signals(signum).name)
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        c.state.pop('controller_status',None);c.state.pop('error',None)
        c.state['controller_identity']=b.process_identity(os.getpid());c.persist()
        b.write(CONTROL/'ACTIVATED.json',{'activated_utc':b.now(),'plan_sha256':b.sha(b.PLAN)})
        b.event('controller_started',pid=os.getpid(),hard_stop=plan['hard_stop_utc'],version=2)
        try:c.run()
        except Exception as error:
            b.event('controller_error',error=repr(error));c.state['error']=repr(error)
        finally:
            c.stop_parallel('V2 controller exiting')
            if c.current and b.owned_process(c.current):c.stop_owned(c.current,'V2 controller exiting')
            try:c.stop_server('V2 controller exiting')
            except Exception as error:
                c.state['infrastructure_cleanup_error']=repr(error);b.event('isolated_server_cleanup_error',error=repr(error))
            c.terminate_primary_at_hardstop()
            c.state['controller_status']='stopped_at_deadline' if time.time()>=c.hard else 'stopped_by_request' if c.shutdown else 'finished_with_recorded_stage_statuses'
            c.persist();b.event('controller_finished',status=c.state['controller_status'])


def launch(args):
    b.require(args.authorize_launch,'Root review and --authorize-launch are required')
    b.verify_plan();require_serial_inactive();CONTROL.mkdir(parents=True,exist_ok=True)
    with (CONTROL/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with (ORIGINAL_CONTROL/'controller.lock').open('a') as shared:
            fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=b.read(b.STATE,{})
        b.require(not(state.get('controller_pid') and state.get('controller_identity') and
                      b.process_identity(state['controller_pid'])==state['controller_identity']),
                  'V2 controller is already active')
        command=['/usr/bin/caffeinate','-i','-s',str(b.PYTHON),str(SCRIPT),'run','--authorize-launch']
        with (CONTROL/'controller.log').open('ab',buffering=0) as stream:
            child=subprocess.Popen(command,cwd=b.ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        record={'pid':child.pid,'identity':b.process_identity(child.pid),'command':command,'launched_utc':b.now(),
                'plan_sha256':b.sha(b.PLAN),'log':str(CONTROL/'controller.log')}
        b.write(CONTROL/'LAUNCH.json',record);print(record)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','check','launch','run'])
    parser.add_argument('--authorize-launch',action='store_true')
    args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='check':b.verify_plan();print('V2 frozen dependencies verified; no work launched.')
    elif args.action=='launch':launch(args)
    else:run_controller(args)

if __name__=='__main__':main()
