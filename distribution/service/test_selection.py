import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('native_selection_service',pathlib.Path(__file__).with_name('selection.py'))
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
class SelectionTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,prepared,selected,deny=False):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'catalog.json'
            path.write_text(json.dumps({'recipient':'fixture','publications':{'three':{}},'selections':[{'publication':'three','authorized_view':'v1','records':prepared}]}))
            s=service.Selector({'catalog':str(path),'recipient':'fixture','authority':'fixture'})
            calls=[]
            async def call(r):
                calls.append(r['op'])
                if r['op']=='pin':return {'view':'v1'}
                if r['op']=='recall':return {'view':'v1','outcome':'hit','response':{'facts':[{'content':'fixture'} for _ in selected]}}
                if deny and calls.count('resolve_local_response')==2:raise RuntimeError('withdrawn')
                return {'view':'v1','refs':selected}
            s.call=call
            result=await s.select('Which approved facts apply?')
            return result,calls
    async def test_exact_all_record_selection_and_cached_reapproval(self):
        refs=[{'namespace':'n','id':str(i),'revision':'1'} for i in range(3)]
        result,calls=await self.exercise(refs,refs)
        self.assertEqual(result['publication'],'three');self.assertEqual(calls.count('resolve_local_response'),2)
    async def test_single_encoded_record_cannot_satisfy_three_selected_records(self):
        refs=[{'namespace':'n','id':str(i),'revision':'1'} for i in range(3)]
        with self.assertRaisesRegex(RuntimeError,'needs preparation'):await self.exercise(refs[:1],refs)
    async def test_revocation_during_cached_selection_rejects(self):
        refs=[{'namespace':'n','id':'1','revision':'1'}]
        with self.assertRaisesRegex(RuntimeError,'withdrawn'):await self.exercise(refs,refs,True)
