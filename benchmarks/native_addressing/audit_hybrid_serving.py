"""Audit frozen complete-hybrid serving coverage independently of runner scores.

This certifies the matching BF16 serving matrix, not the separate INT8 online
research campaign or production authorization. Inputs are immutable evidence.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from hybrid_serving_profile import PROFILE, SYSTEM


def audit(report, suite, selection, measurement=None):
    if (report.get('consumption_profile') != PROFILE or selection.get('consumption_profile') != PROFILE
            or selection.get('system_context') != SYSTEM
            or report.get('system_context_sha256') != hashlib.sha256(SYSTEM.encode()).hexdigest()):
        raise ValueError('consumption profile/context mismatch')
    tasks = suite['tasks']
    by_query = {}
    if len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('duplicate frozen task identity')
    for task in tasks:
        previous = by_query.setdefault(task['query'], task)
        if (previous['answer'],set(previous['expected']),selection['task_bundles'][previous['id']]) != (task['answer'],set(task['expected']),selection['task_bundles'][task['id']]):
            raise ValueError('ambiguous repeated question without task IDs')
    if set(selection['task_bundles']) != {t['id'] for t in tasks}:
        raise ValueError('selection coverage mismatch')
    for task in tasks:
        publication = selection['task_bundles'][task['id']]
        facts = selection['bundle_facts'].get(publication, {'facts': []})['facts']
        actual_refs = {tuple(f['memory_ref'].get(k) for k in ('namespace', 'id', 'revision')) for f in facts}
        expected_refs = {('public-research-fixture', identity, '1') for identity in task['expected']}
        if actual_refs != expected_refs:
            raise ValueError('canonical selection mismatch: ' + task['id'])
    wanted = Counter((by_query[t['query']]['id'], True, turns) for t in tasks for turns in (0, 16, 48))
    wanted.update((by_query[t['query']]['id'], False, 0) for t in tasks)
    observed = Counter()
    probes = Counter()
    for row in report['rows']:
        task = by_query.get(row['query'])
        if task is None:
            raise ValueError('unknown query')
        if row['expected'] != task['answer'] or row['answer'].lower() != task['answer']:
            raise ValueError('incorrect answer: ' + task['id'])
        if row['correct'] is not True:
            raise ValueError('inconsistent runner score')
        if type(row['native']) is not bool:
            raise ValueError('invalid native flag')
        if row['publication'] != selection['task_bundles'][task['id']]:
            raise ValueError('publication/task mismatch')
        tags = [name for name in ('mixed_batch', 'preemption_probe', 'republished', 'development_probe') if row.get(name)]
        if len(tags) > 1:
            raise ValueError('ambiguous probe')
        identity = (task['id'], row['native'], row['turns'])
        if tags:
            probes[(tags[0], *identity)] += 1
        else:
            observed[identity] += 1
    if observed != wanted:
        raise ValueError('missing, duplicate or unexpected matrix row')
    first, third = tasks[0]['id'], tasks[2]['id']
    expected_probes = Counter({('mixed_batch', first, True, 0): 1,
                               ('mixed_batch', third, False, 0): 1,
                               ('preemption_probe', first, True, 48): 1,
                               ('preemption_probe', third, True, 48): 1,
                               ('republished', first, True, 0): 1})
    for task in tasks:
        if task['query'] in ('Which station code is reachable from Merisol outpost?',
                              'Which station code is reachable from Osreth outpost?'):
            expected_probes.update(('development_probe', task['id'], native, turns)
                                  for turns in (16, 48) for native in (True, False))
    if probes != expected_probes:
        raise ValueError('probe coverage mismatch')
    for name in ('context_mismatch_rejected', 'withdrawal_rejected',
                 'revision_mismatch_rejected', 'empty_catalogue_rejected'):
        if report.get(name) is not True:
            raise ValueError('missing control gate: ' + name)
    if report.get('preemptions', 0) < 1:
        raise ValueError('preemption not exercised')
    measured_report = measurement or report
    measured = [r for r in measured_report['rows'] if not r.get('republished')]
    pressure = measured_report.get('pressure_probes', [])
    minimum = 48 * (sum(r['native'] and r['publication'] is not None for r in measured) + len(pressure))
    if report.get('seed_measurement_request_count') != len(measured) + len(pressure):
        raise ValueError('seed measurement boundary mismatch')
    workers = report['metrics']['workers']
    seeds = sum(worker['hybrid_seed_events'] for worker in workers)
    if (report.get('initialization_without_recomputation') != minimum or
            report.get('observed_hybrid_seed_events') != seeds or seeds <= minimum):
        raise ValueError('native recurrent recomputation not demonstrated')
    if report.get('status') != 'passed' or report.get('n') != len(report['rows']) or report.get('correct') != len(report['rows']):
        raise ValueError('incomplete final report')
    config = report['config']
    if not config.get('enable_hybrid_native') or config.get('gguf_weights'):
        raise ValueError('not the matching BF16 hybrid profile')
    return {'status': 'passed', 'tasks': len(tasks), 'distinct_questions': len(by_query), 'canonical_selections': len(tasks),
            'native_matrix_answers': 3 * len(tasks),
            'native_matrix_nonempty_selection_answers': 3 * sum(selection['task_bundles'][t['id']] is not None for t in tasks),
            'native_matrix_empty_selection_answers': 3 * sum(selection['task_bundles'][t['id']] is None for t in tasks),
            'text_control_answers': len(tasks),
            'integration_probe_answers': sum(expected_probes.values()), 'total_answers': len(report['rows']),
            'preemptions': report['preemptions'], 'hybrid_seed_events': seeds,
            'initialization_without_recomputation': minimum,
            'scope': __doc__}


def audit_completion(quality, suite, selection, live):
    """Join retained scored quality with a separate current live integration gate.

    The retained producer's failed pressure-coverage status is never relabelled.
    Compatible admission guards do not change supported-profile neural arithmetic.
    """
    if quality.get('status')!='failed' or quality.get('error')!='native recomputation test did not exercise preemption':
        raise ValueError('unexpected retained quality failure')
    if not live.get('integration_only') or live.get('empty_startup_activated') is not True:
        raise ValueError('initial empty-catalogue activation not exercised')
    if live.get('consumption_profile')!=PROFILE or live.get('system_context_sha256')!=hashlib.sha256(SYSTEM.encode()).hexdigest():
        raise ValueError('live consumption profile/context mismatch')
    for name in ('model','model_revision','library','enable_hybrid_native','host_memory_budget','device_memory_budget','lossless_transport'):
        if quality['config'].get(name)!=live['config'].get(name):
            raise ValueError('quality/live configuration mismatch: '+name)
    def serve_config(report):
        return {k:v for k,v in report['config'].get('serve',{}).items() if k!='num_gpu_blocks_override'}
    if serve_config(quality)!=serve_config(live):
        raise ValueError('quality/live neural execution configuration mismatch')
    tasks=suite['tasks'];first,third=tasks[0],tasks[2]
    expected={('mixed_batch',first['query'],True,0):first['answer'],
              ('mixed_batch',third['query'],False,0):third['answer'],
              ('republished',first['query'],True,0):first['answer']}
    seen=set()
    for row in live['rows']:
        tag='republished' if row.get('republished') else 'mixed_batch' if row.get('mixed_batch') else None
        key=(tag,row['query'],row['native'],row['turns'])
        if key not in expected or key in seen or row['answer'].lower()!=expected[key] or row['correct'] is not True:
            raise ValueError('current live QA/probe coverage mismatch')
        task=first if row['query']==first['query'] else third
        if row['publication']!=selection['task_bundles'][task['id']]:
            raise ValueError('current live publication mismatch')
        seen.add(key)
    if seen!=set(expected) or live.get('status')!='passed' or live.get('n')!=3 or live.get('correct')!=3:
        raise ValueError('incomplete current live gate')
    pressure=live.get('pressure_probes',[])
    if len(pressure)!=2:
        raise ValueError('pressure probe coverage mismatch')
    for probe,task,turns in zip(pressure,(first,third),(32,78)):
        if (probe['query']!=task['query'] or probe['publication']!=selection['task_bundles'][task['id']]
            or probe['native'] is not True or probe['turns']!=turns
            or probe.get('forced_tokens')!=40 or probe.get('quality_scored') is not False
            or probe['usage']['completion_tokens']!=40):
            raise ValueError('invalid mechanical pressure probe')
    republished=next(row for row in live['rows'] if row.get('republished'))
    # Audit the retained matrix plus its four scored concurrency observations,
    # and the newly observed republishing answer. Live mixed answers are checked
    # separately above; pressure continuations never enter QA denominators.
    merged={**quality,**{k:live[k] for k in ('metrics','preemptions','seed_measurement_request_count',
            'initialization_without_recomputation','observed_hybrid_seed_events',
            'context_mismatch_rejected','withdrawal_rejected','revision_mismatch_rejected','empty_catalogue_rejected')},
            'rows':[*quality['rows'],republished],'status':'passed',
            'n':len(quality['rows'])+1,'correct':len(quality['rows'])+1}
    result=audit(merged,suite,selection,measurement=live)
    result.update(retained_quality_producer_status=quality['status'],
                  retained_quality_coverage_failure=quality['error'],
                  retained_scored_answers=len(quality['rows']),current_live_scored_answers=3,
                  total_scored_observations=len(quality['rows'])+3,
                  mechanical_pressure_probes=2,pressure_continuations_quality_scored=False,
                  empty_startup_activated=True,
                  scope='Retained frozen quality matrix plus separate current bootstrap, dtype-compatible native use, actual preemption/reseeding and publication control gates; source/configuration identities remain separate.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'suite', 'selection', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--integration-report', help='Separate current live gate after retained quality producer failed only pressure coverage')
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name)) for name in ('report', 'suite', 'selection')}
    inputs=[json.loads(paths[name].read_text()) for name in ('report','suite','selection')]
    if args.integration_report:
        paths['integration_report']=Path(args.integration_report)
        result=audit_completion(*inputs,json.loads(paths['integration_report'].read_text()))
    else:
        result=audit(*inputs)
    result['inputs_sha256'] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    with Path(args.output).open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    print(json.dumps(result))
