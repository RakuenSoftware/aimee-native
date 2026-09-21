from pathlib import Path
import json,re,unittest,collections,importlib.util
ROOT=Path(__file__).resolve().parent
class CorpusTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.change=json.loads((ROOT/'records.json').read_text());cls.rows=cls.change['records']
 def test_real_corpus_is_unique_public_and_sourced(self):
  self.assertGreater(len(self.rows),10000);self.assertEqual(len(self.rows),len({r['id'] for r in self.rows}))
  for r in self.rows:
   self.assertEqual(r['scope'],{'type':'global','value':'_global'});self.assertEqual(r['namespace'],'aimee-general-v1')
   self.assertEqual(r['lifecycle'],'active');self.assertEqual(r['kind'],'fact');self.assertNotIn('CANARY_',r['content'])
   self.assertRegex(r['revision'],r'^[0-9a-f]{64}$');self.assertTrue(r['metadata']['provenance']['source_url'].startswith('https://'))
 def test_no_test_queries_or_contacts_exported(self):
  self.assertNotIn('read_contracts',self.change)
  for r in self.rows:
   self.assertNotIn('@',r['content']);self.assertNotIn('assignee',r['metadata']['semantic']);self.assertNotIn('contact',r['metadata']['semantic'])
 def test_sources_rebuild_byte_identically(self):
  spec=importlib.util.spec_from_file_location('corpus_builder',ROOT/'build.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  before=(ROOT/'records.json').read_bytes();module.build();self.assertEqual(before,(ROOT/'records.json').read_bytes())
 def test_registry_ports_and_source_ranges(self):
  by={r['id']:r for r in self.rows};ssh=by['iana.ssh']['metadata']['semantic']['assignments']
  self.assertIn({'protocol':'tcp','port':22},ssh)
  for r in self.rows:
   s=r['metadata']['semantic']
   if s['domain']=='iana':
    self.assertEqual(len(s['assignments']),len({(a['protocol'],a['port']) for a in s['assignments']}))
    self.assertTrue(all(0<=a['port']<=65535 for a in s['assignments']))
   if s['domain']=='worldbank':self.assertEqual(len(s['id']),3)
if __name__=='__main__':unittest.main()
