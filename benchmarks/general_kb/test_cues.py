"""Publisher cue regressions, including real compiled Go-reader integration."""
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('public_cues', REPO/'knowledge/general-v2/cues.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def place(identity, name, aliases=(), country='US'):
    return dict(namespace='general', id=identity, revision='v1',
                scope=dict(type='global', value='_global'), kind='fact', tier='L3',
                key=f'place {name} {country} {identity}', content=f'{name} fact {identity}',
                lifecycle='active', confidence=1,
                metadata=dict(semantic=dict(domain='geonames',name=name,asciiname=name,
                                            alternate_names=list(aliases),country_code=country)))


class CueTests(unittest.TestCase):
    def test_canonical_names_win_aliases_without_mutating_objects(self):
        rows=[place('1','Nuevo',['Nuevo']),place('2','Ramona',['Nuevo','Other']),
              place('3','Lanne',country='FR'),place('4','Port-de-Lanne',['Lanne'],country='FR')]
        original=copy.deepcopy(rows)
        result=c.compile_cues(rows,'test')
        address=lambda cue: {r['ref']['id'] for r in result if c.normalize_cue(r['cue'])==cue}
        self.assertEqual(address('nuevo us'),{'1'})
        self.assertEqual(address('lanne fr'),{'3'})
        self.assertEqual(address('other us'),{'2'})
        self.assertEqual(rows,original)
        self.assertEqual({json.dumps(r,sort_keys=True) for r in result},
                         {json.dumps(r,sort_keys=True) for r in c.compile_cues(list(reversed(rows)),'test')})

    def test_true_homonyms_and_shared_fallback_aliases_stay_ambiguous(self):
        rows=[place('1','Springfield',['Oldname']),place('2','Springfield',['Oldname']),
              place('3','Elsewhere',['SPRINGFIELD'])]
        result=c.compile_cues(rows,'test')
        for cue in ['springfield us','oldname us']:
            self.assertEqual({r['ref']['id'] for r in result if c.normalize_cue(r['cue'])==cue},{'1','2'})

    def test_reader_normalization_and_namespace_isolation(self):
        self.assertEqual(c.normalize_cue(' İSTANBUL / ΣΟΣ... '),'istanbul / σοσ')
        self.assertEqual(c.normalize_cue('Port-de-Lanne FR.'),'port-de-lanne fr')
        rows=[place('same','Town'),place('same','Town')]
        rows[1]['namespace']='second'
        result=c.compile_cues(rows,'test')
        self.assertEqual({r['ref']['namespace'] for r in result},{'general','second'})

    def test_real_publication_reader_and_ambiguous_fallback(self):
        reader=Path(os.environ.get('AIMEE_IMAGE_READER',REPO/'.local/bin/aimee-memory-image'))
        issuer=Path(os.environ.get('AIMEE_FIXTURE_ISSUER',REPO/'.local/bin/aimee-issue-fixture'))
        rust=Path(os.environ.get('RUST_QWEN',REPO/'target/debug/aimee-qwen'))
        self.assertTrue(all(p.is_file() for p in [reader,issuer,rust]),'build integration binaries first')
        rows=[place('1','Nuevo'),place('2','Ramona',['Nuevo']),place('3','Lanne',country='FR'),
              place('4','Port-de-Lanne',['Lanne'],country='FR'),
              place('5','Springfield'),place('6','Springfield')]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def cli(*args):
                raw = subprocess.check_output([str(reader),*map(str,args)],text=True)
                return json.loads(raw) if raw.strip() else None
            (root/'input.json').write_text(json.dumps(dict(namespace='general',kind='general',generation=1,
                source='synthetic cue regression',coverage=['facts'],records=rows)))
            view=cli('build','--root',root/'source','--input',root/'input.json')['view']
            cli('publish','--root',root/'source','--view',view)
            approval=dict(version=1,id='cues',subject='recipient',policy_epoch='test',source_view=view,
                active=True,valid_until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat(),
                grants=[],reference_cues=c.compile_cues(rows,'test'))
            (root/'plan.json').write_text(json.dumps(dict(authorization=approval,records=rows,reads=[])))
            subprocess.run([str(issuer),'--input',str(root/'plan.json'),'--output',str(root/'grant'),
                '--key',str(root/'key'),'--public-key',str(root/'public')],check=True,stdout=subprocess.DEVNULL)
            cli('compile-authorized','--root',root/'source','--output-root',root/'image',
                '--authorization',root/'grant','--authority-key',root/'public','--subject','recipient','--policy-epoch','test')
            queries=['What about Nuevo US?','Lanne FR','Ramona US','Port-de-Lanne FR','Springfield US']
            requests=[dict(op='begin')]+[dict(op='native_search',query=q,limit=4) for q in queries]
            result=subprocess.run([str(rust),'read-check','--memory-image',str(root/'image'),
                '--image-reader',str(reader),'--read-authority','test','--read-gateway',str(root/'absent')],
                input=''.join(json.dumps(r)+'\n' for r in requests),text=True,capture_output=True,check=True)
            replies=[json.loads(line)['result'] for line in result.stdout.splitlines()]
            for response,identity in zip(replies[1:5],['1','3','2','4']):
                self.assertEqual([f['memory_ref']['id'] for f in response['facts']],[identity])
            self.assertIn('error',replies[5], 'real ambiguity must defer to the authority')


if __name__=='__main__': unittest.main()
