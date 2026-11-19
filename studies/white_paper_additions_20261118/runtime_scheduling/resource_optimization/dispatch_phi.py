#!/usr/bin/env python3
"""Versioned scheduling adapter for the unchanged, frozen Phi experiment."""
from __future__ import annotations
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
TOPIC = BASE / 'topic12'
PLAN = HERE / 'PHI_DISPATCH_PLAN.json'
ENDPOINT = 'http://127.0.0.1:11535'
HARD_STOP = '2026-11-19T21:00:00+00:00'

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def rows(path):
    path = Path(path)
    if not path.exists():
        return []
    # A partial line is an interrupted write, never silently discarded.
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def utc():
    return datetime.now(timezone.utc).isoformat()

def append(path, obj):
    path = Path(path)
    created = not path.exists()
    with path.open('a') as stream:
        stream.write(json.dumps(obj, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    if created:
        fsync_parent(path)

def fsync_parent(path):
    descriptor = os.open(str(Path(path).parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def immutable(path, obj):
    path = Path(path)
    if path.exists():
        require(read(path) == obj, 'Immutable dispatch record differs: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x') as stream:
            stream.write(json.dumps(obj, indent=2, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        fsync_parent(path)

def scientific_module():
    if str(TOPIC) not in sys.path:
        sys.path.insert(0, str(TOPIC))
    spec = importlib.util.spec_from_file_location('frozen_phi_dispatch_source', TOPIC / 'optional_phi.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def validate_resume(tasks, records, attempts):
    intended = {t['id']: t for t in tasks}
    require(len(intended) == len(tasks), 'Duplicate planned task IDs')
    done = {r['id']: r for r in records}
    tried = {r['id']: r for r in attempts}
    require(len(done) == len(records) and len(tried) == len(attempts), 'Duplicate result or dispatch intent')
    require(set(done) <= set(intended) and set(tried) <= set(intended), 'Unknown dispatch task IDs')
    require(set(done) <= set(tried), 'Result has no durable dispatch intent')
    require(not (set(tried) - set(done)), 'Ambiguous prior attempt without a final result; no automatic retry')
    for collection in [done, tried]:
        for ident, row in collection.items():
            task = intended[ident]
            for key in ['seed', 'prompt_sha256', 'parent_text_sha256']:
                require(row.get(key) == task.get(key), 'Existing record or intent changed ' + key)
    return set(done)

def dispatch(tasks, clients, ledger, intents, run_one, deadline_epoch):
    """At most one call per worker; one coordinator writes all final records."""
    existing = rows(ledger)
    done = validate_resume(tasks, existing, rows(intents))
    pending = iter(t for t in tasks if t['id'] not in done)
    count = len(done)
    active = {}
    stopped = None
    exhausted = False
    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        def submit(worker):
            nonlocal exhausted, stopped
            if stopped or exhausted:
                return
            if time.time() >= deadline_epoch - 2:
                stopped = RuntimeError('Common generation deadline reached; unrun cases stay missing')
                return
            try:
                task = next(pending)
            except StopIteration:
                exhausted = True
                return
            intent = {k: task[k] for k in ['id', 'seed', 'prompt_sha256', 'parent_text_sha256']}
            intent.update(worker=worker, dispatched_utc=utc(), phase='before_request')
            append(intents, intent)
            future = pool.submit(run_one, clients[worker], task)
            active[future] = (worker, task)
        for worker in range(len(clients)):
            submit(worker)
        while active:
            finished, _ = wait(active, return_when=FIRST_COMPLETED)
            available = []
            for future in finished:
                worker, task = active.pop(future)
                try:
                    record = future.result()
                    require(record['id'] == task['id'], 'Worker returned a different task')
                    append(ledger, record)
                    count += 1
                    if count % 10 == 0:
                        print(f'Optional Phi rewrites {count}/{len(tasks)}', flush=True)
                except BaseException as error:
                    stopped = stopped or error
                available.append(worker)
            if stopped is None:
                for worker in sorted(available):
                    submit(worker)
        if stopped is not None:
            raise stopped
    actual = rows(ledger)
    validate_resume(tasks, actual, rows(intents))
    require({r['id'] for r in actual} == {t['id'] for t in tasks}, 'Incomplete optional panel')
    return actual

def prepare():
    module = scientific_module()
    module.verify()
    require(not PLAN.exists(), 'Dispatch plan is already frozen')
    require(not (module.OUT / 'records.jsonl').exists(), 'Cannot prepare after Phi test generation starts')
    sources = [Path(__file__), TOPIC/'optional_phi.py', TOPIC/'run_topic12.py',
               module.CLIENT, module.OUT/'PROTOCOL.json', module.OUT/'MODEL_LOCK.json',
               module.OUT/'TEST_LOCK.json', module.OUT/'SELECTED_TEST_MANIFEST.json']
    immutable(PLAN, {
        'prepared_utc': utc(), 'version': 'phi-dispatch-1',
        'input_sha256': {str(p.resolve()): sha(p) for p in sources},
        'base_url': ENDPOINT, 'hard_stop_utc': HARD_STOP, 'workers_allowed': [1, 2],
        'authorization': 'User requested two Mistral and two Phi requests if this reduces total wall time.',
        'amendment': 'Supersedes serial local inference wording only for request scheduling and the isolated localhost endpoint. The original frozen files are retained unchanged. The reviewed supervisor selects one or two workers from a separate frozen timing benchmark before test generation.',
        'unchanged': ['450 selected IDs', 'parent texts', 'prompt and parent hashes', 'per-task seeds',
                      'model digest', 'server version', 'context and decoding settings', 'generation budget',
                      'detector implementations', 'thresholds', 'analysis and missing-outcome rules'],
        'dispatcher': 'Bounded worker clients with separate request/cache files and one durable result writer. A durable task intent precedes each submission. Attempted tasks lacking final records refuse automatic resume. Recorded errors are retained and never retried.',
        'runtime': 'One persisted absolute generation deadline, at most two requests in flight for Phi; downstream detector work requires both generation clients and all isolated-server model work to finish.',
        'limit': 'Request scheduling and batching may change numerical execution; this is not a claim of bit-identical model outputs.'
    })
    print(PLAN)

def verify_plan():
    plan = read(PLAN)
    for path, digest in plan['input_sha256'].items():
        require(sha(path) == digest, 'Frozen dispatch dependency changed: ' + path)
    return plan

def _run_locked(args):
    require(args.authorize_run, 'Reviewed supervisor authorization required')
    plan = verify_plan()
    require(args.base_url == plan['base_url'] == ENDPOINT, 'Unexpected model endpoint')
    require(args.workers in plan['workers_allowed'], 'Unapproved worker count')
    require(args.hard_stop == plan['hard_stop_utc'], 'Global deadline differs')
    module = scientific_module()
    p = module.verify()
    dev = module.core.load(module.OUT/'DEVELOPMENT.json')
    require(dev['status'] == 'ready', 'Phi development not ready')
    lock = read(module.OUT/'TEST_LOCK.json')
    require(sha(module.OUT/'SELECTED_TEST_MANIFEST.json') == lock['selected_manifest_sha256'], 'Selected IDs changed')
    require(sha(module.OUT/'DEVELOPMENT.json') == lock['development_sha256'], 'Development decision changed')
    tasks = read(module.OUT/'SELECTED_TEST_MANIFEST.json')
    ledger = module.OUT/'records.jsonl'
    intents = module.OUT/'DISPATCH_ATTEMPTS.jsonl'
    validate_resume(tasks, rows(ledger), rows(intents))
    start_path = module.OUT/'DISPATCH_EXECUTION_START.json'
    if start_path.exists():
        execution = read(start_path)
        require(execution['workers'] == args.workers and execution['base_url'] == args.base_url,
                'Resume changed the selected dispatch configuration')
        require(execution['dispatch_plan_sha256'] == sha(PLAN), 'Resume changed the dispatch plan')
    else:
        began = time.time()
        execution = {'started_utc': utc(), 'started_epoch': began, 'workers': args.workers,
                     'base_url': args.base_url, 'deadline_epoch': min(began+p['generation_budget_seconds'], datetime.fromisoformat(args.hard_stop).timestamp()),
                     'dispatch_plan_sha256': sha(PLAN)}
        immutable(start_path, execution)
    remaining = execution['deadline_epoch'] - time.time()
    require(remaining > 2, 'Common generation budget expired')
    client_module = module.module(module.CLIENT, 'preserved_phi_worker_client')
    folder = module.OUT/'test_client'
    # Preserve the root metadata files expected by the unchanged analysis.
    manifest_client = client_module.Client(folder, models=[module.MODEL], base_url=args.base_url,
        max_hours=remaining/3600, request_timeout=300, context=p['decoding']['num_ctx'])
    expected = read(module.OUT/'MODEL_LOCK.json')
    require(module.metadata(manifest_client) == expected, 'Model or backend changed after development')
    clients = []
    for worker in range(args.workers):
        client = client_module.Client(folder/f'worker_{worker}', models=[module.MODEL], base_url=args.base_url,
            max_hours=max(0, execution['deadline_epoch']-time.time())/3600, request_timeout=300, context=p['decoding']['num_ctx'])
        require(module.metadata(client) == expected, 'Worker model metadata differs')
        client.deadline = time.monotonic() + max(0, execution['deadline_epoch']-time.time())
        clients.append(client)
    _, parents = module.core.records()
    actual = dispatch(tasks, clients, ledger, intents,
        lambda client, task: module.generate_one(client, p, task, parents[task['parent_id']]), execution['deadline_epoch'])
    statistics = [client.stats() for client in clients]
    module.core.write(module.OUT/'GENERATION_COMPLETE.json', {
        'finished_utc': utc(), 'records_sha256': sha(ledger), 'selected_n': len(tasks),
        'full_planned_n': 450, 'not_selected_runtime': 450-len(tasks),
        'status_counts': dict(collections.Counter(r['status'] for r in actual)),
        'model_lock_sha256': sha(module.OUT/'MODEL_LOCK.json'),
        'client_statistics': {'new_calls': sum(s['new_calls'] for s in statistics),
            'cache_hits': sum(s['cache_hits'] for s in statistics),
            'elapsed_seconds': time.time()-execution['started_epoch'],
            'remaining_seconds': max(0, execution['deadline_epoch']-time.time()), 'workers': statistics},
        'dispatch_provenance': {'plan_sha256': sha(PLAN), 'adapter_sha256': sha(__file__),
            'workers': args.workers, 'base_url': args.base_url, 'attempts_sha256': sha(intents),
            'execution_start_sha256': sha(start_path)}
    })

def run(args):
    import fcntl
    require(args.authorize_run, 'Reviewed supervisor authorization required')
    with (TOPIC/'optional_phi/DISPATCH.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _run_locked(args)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--workers', type=int, choices=[1, 2], default=1)
    parser.add_argument('--base-url', default=ENDPOINT)
    parser.add_argument('--hard-stop', default=HARD_STOP)
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.check:
        verify_plan()
        print('Phi dispatch plan and source hashes verified; no inference performed.')
    else:
        run(args)

if __name__ == '__main__':
    main()
