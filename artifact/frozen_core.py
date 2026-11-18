"""Verbatim function extracts from the frozen checker/portfolio implementation.
No generated text is executed. See provenance/extracted_functions.json.
"""
import hashlib
import json
from types import SimpleNamespace
from scipy.stats import beta

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def _reject_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate JSON key')
        obj[key] = value
    return obj


def strict_json(text):
    if not isinstance(text, str) or len(text) > 50000:
        raise ValueError('missing or oversized response')
    return json.loads(text, object_pairs_hook=_reject_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON number')))


def eval_expr(expr, variables, assignment, depth=0, counter=None):
    """Evaluate a tiny Boolean AST; no eval/exec, attribute access or arbitrary calls."""
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > 127 or depth > 12:
        raise ValueError('expression exceeds 127 nodes or depth 12')
    if isinstance(expr, str):
        if expr not in variables:
            raise ValueError('unknown variable')
        return bool(assignment[variables.index(expr)])
    if type(expr) is bool:
        return expr
    if not isinstance(expr, list) or not expr or not isinstance(expr[0], str):
        raise ValueError('invalid expression node')
    op = expr[0]
    if op == 'not' and len(expr) == 2:
        return not eval_expr(expr[1], variables, assignment, depth + 1, counter)
    if op in ('and', 'or', 'xor') and len(expr) == 3:
        a = eval_expr(expr[1], variables, assignment, depth + 1, counter)
        b = eval_expr(expr[2], variables, assignment, depth + 1, counter)
        return (a and b) if op == 'and' else ((a or b) if op == 'or' else (a != b))
    raise ValueError('operator or arity is not in the Boolean DSL')


def check_candidate(task, text, *, done=True, finish_reason='stop'):
    if not done:
        return {'accepted': False, 'kind': 'incomplete', 'feedback': 'The response did not finish.'}
    if str(finish_reason).lower() in ('length', 'max_tokens', 'token_limit'):
        return {'accepted': False, 'kind': 'truncated', 'feedback': 'The output token cap was reached; produce a compact complete JSON certificate.'}
    try:
        obj = strict_json(text)
        if not isinstance(obj, dict):
            raise ValueError('top level must be one object')
        if task['family'] == 'directed_path':
            if set(obj) != {'path'} or not isinstance(obj['path'], list):
                raise ValueError('use only the key path with a list of node names')
            path = obj['path']; public = task['public']
            if not path or len(path) > public['max_path_nodes'] or any(not isinstance(n, str) for n in path):
                raise ValueError('invalid path length or node type')
            if path[0] != public['start'] or path[-1] != public['goal']:
                return {'accepted': False, 'kind': 'wrong_endpoints', 'feedback': 'The path must begin at the specified start and end at the specified goal.'}
            edges = set(map(tuple, public['edges']))
            for a, b in zip(path, path[1:]):
                if (a, b) not in edges:
                    return {'accepted': False, 'kind': 'invalid_edge', 'feedback': f'The directed edge {a} -> {b} is not present.'}
            return {'accepted': True, 'kind': 'verified', 'feedback': 'Every edge and both endpoints are valid.'}
        if set(obj) != {'expr'}:
            raise ValueError('use only the key expr')
        variables = task['public']['variables']
        for row in task['public']['truth_table']:
            got = int(eval_expr(obj['expr'], variables, row['input']))
            if got != row['output']:
                return {'accepted': False, 'kind': 'counterexample',
                        'feedback': f"Counterexample: input {row['input']} gives {got}; the required output is {row['output']}."}
        return {'accepted': True, 'kind': 'verified', 'feedback': 'The expression is valid on every Boolean input.'}
    except (ValueError, TypeError, KeyError, RecursionError, json.JSONDecodeError) as exc:
        return {'accepted': False, 'kind': 'malformed', 'feedback': str(exc)[:240]}


def _sum_cost(candidates, field):
    vals=[c.get('response',{}).get(field) for c in candidates]
    return sum(v for v in vals if isinstance(v,(int,float))) if all(isinstance(v,(int,float)) for v in vals) else None


def portfolio(task, method, candidates):
    winners=[c for c in candidates if c['verdict']['accepted']]
    return {'task_id':task['task_id'],'family':task['family'],'regime':task['regime'],'method':method,
            'accepted':int(bool(winners)),'candidate_uids':[c['uid'] for c in candidates],
            'certificate_uid':winners[0]['uid'] if winners else None,'model_tags':[c['model'] for c in candidates],
            'scheduled_calls':len(candidates),'invalid_candidates':sum(not c['verdict']['accepted'] for c in candidates),
            'request_errors':sum(c['verdict']['kind']=='request_error' for c in candidates),
            'prompt_tokens':_sum_cost(candidates,'prompt_tokens'),'output_tokens':_sum_cost(candidates,'output_tokens'),
            'total_seconds':_sum_cost(candidates,'total_seconds'),'eval_seconds':_sum_cost(candidates,'eval_seconds'),
            'prompt_eval_seconds':_sum_cost(candidates,'prompt_eval_seconds'),'load_seconds':_sum_cost(candidates,'load_seconds'),
            'request_wall_seconds':_sum_cost(candidates,'wall_seconds'),
            'checker_seconds':sum(c['checker_seconds'] for c in candidates)}


def exact_solve(task):
    """Classical solver baseline using public inputs only, never stored solutions."""
    public=task['public']
    if task['family']=='directed_path':
        neighbors={}
        for a,b in public['edges']:neighbors.setdefault(a,[]).append(b)
        queue=[[public['start']]];seen={public['start']}
        for path in queue:
            if path[-1]==public['goal']:return {'path':path}
            if len(path)>=public['max_path_nodes']:continue
            for node in neighbors.get(path[-1],[]):
                if node not in seen:
                    seen.add(node);queue.append(path+[node])
        raise ValueError('No feasible path found')
    variables=public['variables'];table=public['truth_table']
    target=1 if sum(r['output'] for r in table)<=len(table)/2 else 0
    def balanced(op,items):
        if len(items)==1:return items[0]
        middle=len(items)//2
        return [op,balanced(op,items[:middle]),balanced(op,items[middle:])]
    terms=[]
    for row in table:
        if row['output']==target:
            terms.append(balanced('and',[v if bit else ['not',v] for v,bit in zip(variables,row['input'])]))
    expr=balanced('or',terms) if terms else False
    return {'expr':expr if target else ['not',expr]}

import itertools
legacy = SimpleNamespace(strict_json=strict_json, eval_expr=eval_expr, check_candidate=check_candidate)

def _balanced(op, terms):
    if len(terms) == 1:
        return terms[0]
    middle = len(terms) // 2
    return [op, _balanced(op, terms[:middle]), _balanced(op, terms[middle:])]


def normalize_associative(expr, variables, depth=0, counter=None):
    """Only reassociate complete n-ary AND/OR/XOR. No operator/value repair."""
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > 512 or depth > 24:
        raise ValueError('diagnostic expression exceeds traversal limit')
    if type(expr) is bool or (isinstance(expr, str) and expr in variables):
        return expr
    if not isinstance(expr, list) or not expr:
        raise ValueError('invalid expression node')
    op = expr[0]
    if op == 'not' and len(expr) == 2:
        return [op, normalize_associative(expr[1], variables, depth + 1, counter)]
    if op in ('and', 'or', 'xor') and len(expr) >= 3:
        return _balanced(op, [normalize_associative(t, variables, depth + 1, counter)
                              for t in expr[1:]])
    raise ValueError('unsupported operator or arity')


def _extended_value(expr, variables, assignment):
    """Independent total semantics for the diagnostic's n-ary grammar."""
    if type(expr) is bool:
        return expr
    if isinstance(expr, str):
        return bool(assignment[variables.index(expr)])
    op = expr[0]
    args = [_extended_value(x, variables, assignment) for x in expr[1:]]
    if op == 'not':
        return not args[0]
    if op == 'and':
        return all(args)
    if op == 'or':
        return any(args)
    if op == 'xor':
        return sum(args) % 2 == 1
    raise ValueError('unsupported operator')


def diagnose_candidate(task, record):
    response = record.get('response', {})
    text = response.get('text', '')
    result = {'uid': record.get('uid'), 'task_id': task['task_id'],
              'family': task['family'], 'original_kind': record['verdict']['kind'],
              'original_accepted': bool(record['verdict']['accepted']),
              'category': None, 'normalization_attempted': False,
              'recoverable_complete_certificate': False}
    if record['verdict']['kind'] == 'request_error':
        result['category'] = 'request_error'
        return result
    if not response.get('done', False) or str(response.get('finish_reason')).lower() in ('length', 'max_tokens', 'token_limit'):
        result['category'] = 'incomplete_or_truncated'
        return result
    try:
        obj = legacy.strict_json(text)
    except (ValueError, TypeError, RecursionError):
        result['category'] = 'invalid_json'
        return result
    if result['original_accepted']:
        result['category'] = 'originally_verified'
        return result
    if task['family'] != 'boolean_program':
        result['category'] = ('well_formed_semantic_failure' if result['original_kind'] != 'malformed'
                              else 'invalid_schema_or_path_type')
        return result
    if not isinstance(obj, dict) or set(obj) != {'expr'}:
        result['category'] = 'invalid_schema'
        return result
    if result['original_kind'] == 'counterexample':
        result['category'] = 'well_formed_semantic_failure'
        return result
    result['category'] = 'invalid_ast_operator_arity_or_type'
    try:
        variables = task['public']['variables']
        normalized = normalize_associative(obj['expr'], variables)
        if normalized == obj['expr']:
            return result
        # Complete truth-table equality proves this narrow transformation preserves
        # the extended grammar's meaning, not that the original DSL permitted it.
        for assignment in itertools.product((0, 1), repeat=len(variables)):
            if _extended_value(obj['expr'], variables, assignment) != legacy.eval_expr(normalized, variables, assignment):
                raise AssertionError('Diagnostic normalization changed semantics')
        result['normalization_attempted'] = True
        normalized_text = canonical({'expr': normalized})
        checked = legacy.check_candidate(task, normalized_text)
        result['normalized_kind'] = checked['kind']
        result['recoverable_complete_certificate'] = bool(checked['accepted'])
        result['normalized_candidate'] = normalized_text
    except (ValueError, TypeError, IndexError, RecursionError):
        pass
    return result


def conservative_comparison(rows, method, baseline, alpha=.025):
    paired = {}
    for row in rows:
        if row['method'] in (method, baseline):
            paired.setdefault(row['task_id'], {})[row['method']] = row
    pairs = [v for v in paired.values() if len(v) == 2]
    if not pairs:
        return {'method': method, 'baseline': baseline, 'n': 0}
    groups = {}
    for pair in pairs:
        row = pair[method]
        groups.setdefault((row['family'], row['regime']), []).append(
            row['accepted'] - pair[baseline]['accepted'])
    tail = alpha / (4 * len(groups))
    lower = upper = total = 0.0
    details = []
    for (family, grade), differences in sorted(groups.items()):
        n = len(differences)
        positive = sum(d > 0 for d in differences)
        negative = sum(d < 0 for d in differences)
        def limits(k):
            return (0.0 if k == 0 else float(beta.ppf(tail, k, n-k+1)),
                    1.0 if k == n else float(beta.ppf(1-tail, k+1, n-k)))
        pl, pu = limits(positive)
        nl, nu = limits(negative)
        weight = n / len(pairs)
        lower += weight * (pl - nu)
        upper += weight * (pu - nl)
        total += sum(differences)
        details.append({'family': family, 'grade': grade, 'n': n,
                        'positive_discordance': positive, 'negative_discordance': negative})
    return {'method': method, 'baseline': baseline, 'n': len(pairs),
            'difference': total / len(pairs), 'interval_level': 1-alpha,
            'conservative_paired_interval': [lower, upper],
            'above_five_point_margin': lower > .05, 'strata': details}
