import hashlib,json,tempfile,unittest
from pathlib import Path
from audit_live_native_extension import audit
from hybrid_serving_profile import SYSTEM


class LiveAuditTests(unittest.TestCase):
    def fixture(self,root):
        config={'model':'model'};tasks={'tasks':[{'id':'one','query':'What is the code?','answer':'7391'}]}
        facts=[{'content':'The code is 7391.'}]
        selection={'task_bundles':{'one':'bundle'},'bundle_facts':{'bundle':{'facts':facts}}}
        inputs={'config':config,'tasks':tasks,'selections':selection,'heldout':{'cases':[]}}
        hashes={}
        for name,value in inputs.items():
            raw=json.dumps(value).encode();(root/(name+'.json')).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
        rows=[]
        for turns in (0,16,48):
            for native in (True,False):
                context=SYSTEM if native else SYSTEM+'\n\nAuthoritative memory:\nThe code is 7391.'
                messages=[{'role':'system','content':context}]
                for _ in range(turns):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
                messages.append({'role':'user','content':'What is the code?'})
                body={'model':'model','messages':messages,'temperature':0,'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False}}
                if native:body['vllm_xargs']={'aimee_publication':'bundle'}
                rows.append({'id':'one','query':'What is the code?','expected':'7391','answer':'7391','correct':True,'native':native,'turns':turns,'publication':'bundle',
                             'source_facts_sha256':hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest(),
                             'request_sha256':hashlib.sha256(json.dumps(body).encode()).hexdigest()})
        (root/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        (root/'report.json').write_text(json.dumps({'inputs':hashes,'status':'passed','n':6,'correct':6}))
        return rows

    def test_complete_matrix_is_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root);self.assertEqual(audit(root)['rows'],6)

    def test_missing_duplicate_and_modified_prompt_are_rejected(self):
        for change in ('missing','duplicate','prompt','facts'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);rows=self.fixture(root)
                if change=='missing':rows.pop()
                if change=='duplicate':rows[-1]=rows[0]
                if change=='prompt':rows[0]['request_sha256']='0'*64
                if change=='facts':rows[0]['source_facts_sha256']='0'*64
                (root/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                with self.assertRaises(ValueError):audit(root)

    def test_incorrect_answers_remain_valid_failed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rows=self.fixture(root);rows[0].update(answer='unknown',correct=False)
            (root/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            report=json.loads((root/'report.json').read_text());report.update(status='quality_failed',correct=5)
            (root/'report.json').write_text(json.dumps(report))
            self.assertEqual(audit(root)['quality_status'],'quality_failed')

if __name__=='__main__':unittest.main()
