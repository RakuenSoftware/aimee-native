import copy
import hashlib
from hybrid_serving_profile import PROFILE, SYSTEM
import unittest
from audit_hybrid_serving import audit, audit_completion


class HybridServingAuditTests(unittest.TestCase):
    def setUp(self):
        tasks = [dict(id=str(i), query='query' + str(i), answer=str(i), expected=[str(i)]) for i in range(3)]
        self.suite = {'tasks': tasks}
        self.selection = {'task_bundles': {t['id']: t['id'] for t in tasks},
                          'bundle_facts': {t['id']: {'facts': [{'memory_ref': {'namespace': 'public-research-fixture', 'id': t['id'], 'revision': '1'}}]} for t in tasks}}
        self.selection.update(consumption_profile=PROFILE, system_context=SYSTEM)
        def row(task, native, turns, **extra):
            return dict(publication=task['id'], query=task['query'], answer=task['answer'],
                        expected=task['answer'], correct=True, native=native, turns=turns, **extra)
        rows = [row(t, True, turns) for t in tasks for turns in (0, 16, 48)]
        rows += [row(t, False, 0) for t in tasks]
        rows += [row(tasks[0], True, 0, mixed_batch=True), row(tasks[2], False, 0, mixed_batch=True),
                 row(tasks[0], True, 48, preemption_probe=True), row(tasks[2], True, 48, preemption_probe=True)]
        minimum = 48 * sum(r['native'] for r in rows)
        rows.append(row(tasks[0], True, 0, republished=True))
        self.report = dict(rows=rows, status='passed', n=len(rows), correct=len(rows), preemptions=1,
                           context_mismatch_rejected=True, withdrawal_rejected=True,
                           revision_mismatch_rejected=True, empty_catalogue_rejected=True,
                           seed_measurement_request_count=len(rows)-1,
                           initialization_without_recomputation=minimum,
                           observed_hybrid_seed_events=minimum+48,
                           metrics={'workers': [{'hybrid_seed_events': minimum+48}]},
                           config={'enable_hybrid_native': True}, consumption_profile=PROFILE,
                           system_context_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest())

    def test_complete_matrix(self):
        self.assertEqual(audit(self.report, self.suite, self.selection)['total_answers'], 17)

    def test_runner_boolean_cannot_hide_wrong_answer(self):
        self.report['rows'][0]['answer'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'incorrect answer'):
            audit(self.report, self.suite, self.selection)

    def test_duplicate_cannot_replace_missing_row(self):
        self.report['rows'][1] = copy.deepcopy(self.report['rows'][0])
        with self.assertRaisesRegex(ValueError, 'matrix row'):
            audit(self.report, self.suite, self.selection)

    def test_routing_score_cannot_hide_wrong_canonical_selection(self):
        self.selection['bundle_facts']['0']['facts'][0]['memory_ref']['id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'canonical selection'):
            audit(self.report, self.suite, self.selection)

    def test_preemption_requires_native_reseeding(self):
        minimum = self.report['initialization_without_recomputation']
        self.report['observed_hybrid_seed_events'] = minimum
        self.report['metrics']['workers'][0]['hybrid_seed_events'] = minimum
        with self.assertRaisesRegex(ValueError, 'recomputation'):
            audit(self.report, self.suite, self.selection)

    def test_missing_live_revision_gate_rejected(self):
        del self.report['revision_mismatch_rejected']
        with self.assertRaisesRegex(ValueError, 'control gate'):
            audit(self.report, self.suite, self.selection)

    def test_changed_instruction_contract_cannot_reuse_old_report(self):
        self.report['system_context_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'profile/context'):
            audit(self.report, self.suite, self.selection)

    def test_matching_record_id_with_wrong_revision_is_rejected(self):
        self.selection['bundle_facts']['0']['facts'][0]['memory_ref']['revision'] = '2'
        with self.assertRaisesRegex(ValueError, 'canonical selection'):
            audit(self.report, self.suite, self.selection)

    def completed_pair(self):
        quality=copy.deepcopy(self.report)
        quality['rows']=quality['rows'][:-1]
        quality.update(status='failed',error='native recomputation test did not exercise preemption')
        live=copy.deepcopy(self.report)
        live['rows']=[live['rows'][-5],live['rows'][-4],live['rows'][-1]]
        live.update(integration_only=True,empty_startup_activated=True,n=3,correct=3,
                    seed_measurement_request_count=4,initialization_without_recomputation=144,
                    observed_hybrid_seed_events=192,metrics={'workers':[{'hybrid_seed_events':192}]})
        live['pressure_probes']=[dict(query='query'+str(i),publication=str(i),native=True,turns=t,
            forced_tokens=40,quality_scored=False,usage={'completion_tokens':40}) for i,t in ((0,32),(2,78))]
        return quality,live

    def test_retained_quality_and_current_live_gates_are_audited_separately(self):
        quality,live=self.completed_pair()
        result=audit_completion(quality,self.suite,self.selection,live)
        self.assertEqual(result['retained_quality_producer_status'],'failed')
        self.assertEqual(result['current_live_scored_answers'],3)
        self.assertFalse(result['pressure_continuations_quality_scored'])
        self.assertEqual(result['hybrid_seed_events'],192)

    def test_unexercised_forced_pressure_boundary_is_rejected(self):
        quality,live=self.completed_pair()
        live['pressure_probes'][0]['usage']['completion_tokens']=5
        with self.assertRaisesRegex(ValueError,'pressure'):
            audit_completion(quality,self.suite,self.selection,live)

    def test_declared_repeated_question_requires_exact_matrix_multiplicity(self):
        task = copy.deepcopy(self.suite['tasks'][1])
        task['id'] = 'repeated'
        self.suite['tasks'].append(task)
        self.selection['task_bundles']['repeated'] = '1'
        extra = [copy.deepcopy(row) for row in self.report['rows']
                 if row['query'] == task['query']]
        self.report['rows'].extend(extra)
        self.report['n'] += 4
        self.report['correct'] += 4
        self.report['seed_measurement_request_count'] += 4
        self.report['initialization_without_recomputation'] += 144
        self.report['observed_hybrid_seed_events'] += 144
        self.report['metrics']['workers'][0]['hybrid_seed_events'] += 144
        result = audit(self.report, self.suite, self.selection)
        self.assertEqual((result['tasks'], result['distinct_questions']), (4, 3))
        self.report['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'matrix row'):
            audit(self.report, self.suite, self.selection)
