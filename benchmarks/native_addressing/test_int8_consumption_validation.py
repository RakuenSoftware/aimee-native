import copy
import hashlib
import unittest
from hybrid_serving_profile import SYSTEM
from int8_consumption_validation import audit


class Int8ConsumptionAuditTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [{'id': 'known', 'answer': '1234', 'expected': ['station']},
                      {'id': 'missing', 'answer': 'unknown', 'expected': []}]
        self.rows = [dict(task=t['id'], phase=phase, native=native, turns=turns,
                         expected=t['answer'], answer=t['answer'], correct=True,
                         selected_refs=[['public-research-fixture', name, '1'] for name in t['expected']] if native else [],
                         memory_encoding_passes=0,
                         system_context_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest() if native else None)
                     for t in self.tasks for phase, native in [('online', True), ('online', False), ('prepared', True)]
                     for turns in (0, 16, 48)]

    def test_failed_answers_remain_complete_measured_failure(self):
        self.rows[0].update(answer='unknown', correct=False)
        result = audit(self.rows, self.tasks)
        self.assertEqual((result['status'], result['n'], result['correct']), ('failed', 18, 17))
        self.assertEqual(len(result['failures']), 1)
        self.assertEqual(result['groups']['online-text']['correct'], 6)

    def test_missing_cell_cannot_be_replaced_by_duplicate(self):
        self.rows[1] = copy.deepcopy(self.rows[0])
        with self.assertRaisesRegex(ValueError, 'matrix'): audit(self.rows, self.tasks)

    def test_wrong_revision_or_prepared_encoding_invalidates_quality_gate(self):
        self.rows[0]['selected_refs'][0][2] = '2'
        with self.assertRaisesRegex(ValueError, 'selection'): audit(self.rows, self.tasks)
        self.rows[0]['selected_refs'][0][2] = '1'
        next(r for r in self.rows if r['phase'] == 'prepared')['memory_encoding_passes'] = 1
        with self.assertRaisesRegex(ValueError, 'encoded'): audit(self.rows, self.tasks)

    def test_empty_native_selection_still_binds_instruction_contract(self):
        self.assertEqual(audit(self.rows, self.tasks)['status'], 'passed')
        next(r for r in self.rows if r['task'] == 'missing' and r['native'])['system_context_sha256'] = None
        with self.assertRaisesRegex(ValueError, 'binding'): audit(self.rows, self.tasks)

    def test_independent_trace_verification_rejects_changed_payload(self):
        import tempfile
        import json
        from pathlib import Path
        from audit_int8_consumption import verify
        from hybrid_serving_profile import PROFILE
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            suite = root / 'suite.json'; suite.write_text(json.dumps({'tasks': self.tasks}))
            protocol = {'tasks': self.tasks, 'profile': PROFILE, 'system_context': SYSTEM,
                        'precision': 'rowwise INT8 research runtime', 'schedule': 'preload-only',
                        'turns': [0, 16, 48], 'suite_sha256': hashlib.sha256(suite.read_bytes()).hexdigest(),
                        'binary_sha256': 'binary', 'reader_sha256': 'reader'}
            (root / 'protocol.json').write_text(json.dumps(protocol))
            fact = {'content': 'Station access code is 1234.', 'memory_ref': {'namespace': 'public-research-fixture', 'id': 'station', 'revision': '1'}}
            selection = {'task_bundles': {'known': 'bank', 'missing': None}, 'bundle_facts': {'bank': {'facts': [fact]}},
                         'system_context': SYSTEM, 'consumption_profile': PROFILE}
            (root / 'selection.json').write_text(json.dumps(selection))
            for phase in ('online', 'prepared'):
                (root / (phase + '-invocation.json')).write_text(json.dumps({'argv': ['binary', '--int8', '--enable-hybrid-native']}))
            for index, row in enumerate(self.rows):
                trace = {'answer': row['answer'], 'recall_events': [{'aimee_response': {'facts': [
                    {'memory_ref': dict(zip(('namespace', 'id', 'revision'), ref)), 'content': fact['content']} for ref in row['selected_refs']]}}],
                    'memory_encoding_passes': row['memory_encoding_passes'],
                    'native_system_context_sha256': row['system_context_sha256'],
                    'native_recurrent_state': True if row['native'] else None,
                    'generation_prompt': '<|im_start|>system\n' + (SYSTEM + '\n\nAuthoritative memory:\n' + (fact['content'] if row['task'] == 'known' else '')).strip() + '<|im_end|>\n'}
                path = root / (str(index) + '.json'); path.write_text(json.dumps(trace))
                row.update(trace=path.name, trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            result = audit(self.rows, self.tasks)
            result.update(rows=self.rows, protocol_sha256=hashlib.sha256((root / 'protocol.json').read_bytes()).hexdigest())
            (root / 'report.json').write_text(json.dumps(result))
            self.assertEqual(verify(root, suite)['trace_hashes_verified'], 18)
            (root / '0.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'trace hash'): verify(root, suite)
