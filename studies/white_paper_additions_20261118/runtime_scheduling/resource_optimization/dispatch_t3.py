"""Runtime-only T3 replication dispatcher. Scientific functions remain unchanged."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import copy
import fcntl
import json
import os
from pathlib import Path
import random
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'topic3'))
import t3a_bridge as study

ORIGINAL_EXECUTE=study.execute
ORIGINAL_CLIENT=study.SweepClient


def durable_append(path,record):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    existed=path.exists()
    with path.open('a') as stream:
        stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    if not existed:
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)


def identity(record):
    return record['task_id'],record['configuration'],record['slot']


def schedule_for(tasks,configurations,schedule_seed):
    schedule=[(task,config,slot) for task in tasks for config in configurations for slot in range(study.SLOTS)]
    random.Random(schedule_seed).shuffle(schedule)
    return schedule


def clone_client(client,index):
    worker=copy.copy(client)
    worker.out=client.out/f'test_worker_{index}'
    worker.out.mkdir(parents=True,exist_ok=True)
    worker.cache=worker.out/'cache'
    worker.cache.mkdir(exist_ok=True)
    worker.calls=0
    worker.cache_hits=0
    study.immutable(worker.out/'MODEL_MANIFEST.json',worker.metadata)
    study.immutable(worker.out/'SERVER_VERSION.json',worker.version)
    # Copying preserves the exact common monotonic deadline and request timeout.
    assert worker.deadline==client.deadline
    return worker


def execute_tests(client,model,tasks,configurations,logpath,schedule_seed,workers,
                  worker_factory=clone_client):
    """Dispatch the original shuffled schedule; commit responses with one writer.

    Every dispatch has an fsynced intent first. If a prior intent has no result,
    resume refuses rather than retrying a possibly completed request. Request
    errors are normal failed observations and are never retried.
    """
    if workers not in (1,2):
        raise ValueError('Only one or two workers are permitted')
    logpath=Path(logpath)
    schedule=schedule_for(tasks,configurations,schedule_seed)
    expected={(t['task_id'],c['name'],s) for t,c,s in schedule}
    if len(expected)!=len(schedule):
        raise RuntimeError('Duplicate identities in planned schedule')
    records=study.rows(logpath)
    existing={identity(r) for r in records}
    if len(existing)!=len(records) or not existing<=expected:
        raise RuntimeError('Unknown or duplicate committed test record')
    taskmap={t['task_id']:t for t in tasks}
    for record in records:
        if record['task_sha256']!=taskmap[record['task_id']]['task_sha256']:
            raise RuntimeError('Committed test task hash changed')
    intents_path=logpath.parent/'test_dispatch_intents.jsonl'
    intents=study.rows(intents_path)
    attempted={identity(r) for r in intents}
    if len(attempted)!=len(intents) or not attempted<=expected:
        raise RuntimeError('Unknown or duplicate dispatch intent')
    if attempted-existing:
        raise RuntimeError('Ambiguous prior attempt has no committed result. Resume and retry are refused.')
    if existing-attempted:
        raise RuntimeError('Committed result has no durable dispatch intent')
    schedule_map={(t['task_id'],c['name'],s):(index,t,c,s)
                  for index,(t,c,s) in enumerate(schedule)}
    for intent in intents:
        index,task,config,slot=schedule_map[identity(intent)]
        required=dict(schedule_index=index,task_sha256=task['task_sha256'],
            seed=task['seed']*10+slot,prompt_sha256=study.old.digest(study.prompt(task,config['supplied'],slot)),
            temperature=config['temperature'],top_p=config['top_p'],model=model,
            model_digest=client.metadata[model]['digest'])
        if any(intent.get(key)!=value for key,value in required.items()) or intent.get('worker') not in range(workers):
            raise RuntimeError('Prior dispatch intent differs from the original task payload or schedule')
    for record in records:
        _,task,_,slot=schedule_map[identity(record)]
        if record['response'].get('seed')!=task['seed']*10+slot:
            raise RuntimeError('Committed response seed differs from the original task')
    schedule_record=dict(
        original_code=study.code_manifest(),dispatcher_sha256=study.sha(__file__),
        workers=workers,base_url=client.base,model=model,
        model_digest=client.metadata[model]['digest'],backend_version=client.version,
        schedule_seed=schedule_seed,task_digest=study.old.digest(tasks),
        configurations=configurations,calls_per_configuration=study.SLOTS,
        ordered_identities=[[t['task_id'],c['name'],s] for t,c,s in schedule],
        test_protocol_sha256=study.sha(logpath.parent/'TEST_PROTOCOL.json') if (logpath.parent/'TEST_PROTOCOL.json').exists() else None,
        execution_start_sha256=study.sha(logpath.parent/'EXECUTION_START.json') if (logpath.parent/'EXECUTION_START.json').exists() else None,
        deadline_policy='All workers share the base client absolute execution deadline and request timeout.',
        intent_policy='Durable intent before dispatch. Any unmatched intent prevents resume. No request retries.')
    study.immutable(logpath.parent/'T3_TEST_DISPATCH_SCHEDULE.json',schedule_record)
    clients=[worker_factory(client,i) for i in range(workers)]
    todo=iter((index,t,c,s) for index,(t,c,s) in enumerate(schedule)
              if (t['task_id'],c['name'],s) not in existing)
    pending={}
    stopped=False
    committed=len(existing)

    def dispatch(pool,worker_index):
        nonlocal stopped
        if stopped or client.deadline-time.monotonic()<=2:
            stopped=True
            return False
        try:
            index,task,config,slot=next(todo)
        except StopIteration:
            return False
        prompt=study.prompt(task,config['supplied'],slot)
        seed=task['seed']*10+slot
        intent=dict(task_id=task['task_id'],configuration=config['name'],slot=slot,
            schedule_index=index,worker=worker_index,task_sha256=task['task_sha256'],
            seed=seed,prompt_sha256=study.old.digest(prompt),temperature=config['temperature'],
            top_p=config['top_p'],model=model,model_digest=client.metadata[model]['digest'],
            recorded_at=study.stamp())
        durable_append(intents_path,intent)
        future=pool.submit(clients[worker_index].generate_sweep,model,prompt,seed,
                           config['temperature'],config['top_p'])
        pending[future]=(worker_index,task,config,slot,seed,time.monotonic())
        return True

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index in range(workers):
            dispatch(pool,index)
        while pending:
            finished,_=wait(pending,return_when=FIRST_COMPLETED)
            # Stable commit order among simultaneously returned futures. Request
            # issuance always advances the original shuffled schedule in order.
            finished=sorted(finished,key=lambda f:pending[f][0])
            for future in finished:
                index,task,config,slot,seed,started=pending.pop(future)
                try:
                    response=future.result()
                except study.local_models.BudgetExceeded as exc:
                    stopped=True
                    durable_append(logpath.parent/'test_dispatch_events.jsonl',dict(
                        event='budget_stopped_after_intent',task_id=task['task_id'],
                        configuration=config['name'],slot=slot,error=repr(exc),recorded_at=study.stamp(),
                        retry_forbidden=True))
                    continue
                except Exception as exc:
                    response=dict(text='',done=False,finish_reason='request_error',model=model,
                        model_digest=client.metadata[model]['digest'],seed=seed,
                        wall_seconds=time.monotonic()-started,error=repr(exc),dispatch_exception=True)
                    durable_append(clients[index].out/'DISPATCH_ERRORS.jsonl',response)
                verdict=study.old.check_candidate(task,response.get('text',''),
                    done=response.get('done',False),finish_reason=response.get('finish_reason','unknown'))
                durable_append(logpath,dict(task_id=task['task_id'],depth=task['bridge_depth'],
                    configuration=config['name'],slot=slot,task_sha256=task['task_sha256'],
                    response=response,verdict=verdict,recorded_at=study.stamp()))
                committed+=1
                client.calls+=1
                if committed%25==0:
                    print(f'{logpath.stem}: {committed}/{len(schedule)} committed calls',flush=True)
            for index in sorted(set(range(workers))-{item[0] for item in pending.values()}):
                dispatch(pool,index)
    return committed==len(schedule)


def main():
    parser=argparse.ArgumentParser(description=__doc__,add_help=False)
    parser.add_argument('--workers',type=int,choices=(1,2),required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:11535')
    options,original_args=parser.parse_known_args()
    original_parser=argparse.ArgumentParser(add_help=False)
    original_parser.add_argument('phase',choices=['replicate'])
    original_parser.add_argument('--out',type=Path,required=True)
    original_parser.add_argument('--replicate-from',type=Path,required=True)
    original_parser.add_argument('--model',choices=['mistral-small3.2:24b'],required=True)
    original_parser.add_argument('--authorize-run',action='store_true')
    selected,_=original_parser.parse_known_args(original_args)
    if options.base_url!='http://127.0.0.1:11535':
        raise RuntimeError('This dispatcher requires the reviewed isolated localhost endpoint')
    if not selected.authorize_run or not (HERE.parent/'DECISIONS.json').exists():
        raise RuntimeError('The original authorization guard is required')
    selected.out.mkdir(parents=True,exist_ok=True)
    lock=(selected.out/'T3_DISPATCH.lock').open('a+')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError('Another dispatcher owns this run directory') from exc
    lock.seek(0);lock.truncate();lock.write(str(os.getpid())+'\n');lock.flush();os.fsync(lock.fileno())
    plan_path=selected.out/'T3_DISPATCH_PLAN.json'
    if (selected.out/'test_calls.jsonl').exists() and not plan_path.exists():
        raise RuntimeError('Cannot introduce a new scheduler after an unamended test run started')
    plan=dict(dispatcher_sha256=study.sha(__file__),original_code=study.code_manifest(),
        workers=options.workers,base_url=options.base_url,
        source_protocol_sha256=study.sha(selected.replicate_from/'TEST_PROTOCOL.json'),
        amendment='Runtime scheduling only. Development timing and replication freeze remain serial. Scientific tasks, per-call payloads, seeds, exact checker and statistics are unchanged.',
        worker_selection='Chosen by the external reviewed controller operational benchmark, never by scientific outcomes.',
        numerical_execution='Concurrent request order and backend batching may change numerical execution. Bit-identical model outputs are not asserted.',
        record_writing='Single durable test result writer. Separate per-worker raw request ledgers.',
        resume='Unmatched durable dispatch intent is ambiguous and prevents resume. Recorded errors are never retried.',
        deadline='All workers use the original execution clock and common request deadline.')
    study.immutable(plan_path,plan)

    class EndpointClient(ORIGINAL_CLIENT):
        def __init__(self,*args,**kwargs):
            kwargs['base_url']=options.base_url
            super().__init__(*args,**kwargs)

    def routed_execute(client,model,tasks,configurations,logpath,schedule_seed):
        if Path(logpath).name!='test_calls.jsonl':
            return ORIGINAL_EXECUTE(client,model,tasks,configurations,logpath,schedule_seed)
        return execute_tests(client,model,tasks,configurations,logpath,schedule_seed,options.workers)

    study.SweepClient=EndpointClient
    study.execute=routed_execute
    sys.argv=[str(Path(study.__file__)),*original_args]
    study.main()


if __name__=='__main__':
    main()
