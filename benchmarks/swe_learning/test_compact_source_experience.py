import pathlib
import subprocess
import tempfile
import unittest
from source_experience import compact_patch_command,patch_command,accept_success


class CompactSourceExperience(unittest.TestCase):
 def test_multifile_insert_replace_delete_is_byte_exact_on_clean_base(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory)
   def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True,stderr=subprocess.DEVNULL)
   git('init');git('config','user.email','fixture@example.invalid');git('config','user.name','Fixture')
   original={name:[f'{name} line {i} with stable surrounding context\n' for i in range(90)] for name in ['first.txt','second.txt']}
   for name,lines in original.items():(root/name).write_text(''.join(lines))
   git('add','.');git('commit','-m','base')
   first=original['first.txt'].copy();first[70:71]=[];first[20:21]=['replacement\n'];first[0:0]=['inserted first\n']
   second=original['second.txt'].copy();second[50:50]=['repeated\n','repeated\n'];second[3:5]=['new block\n']
   expected={'first.txt':''.join(first),'second.txt':''.join(second)}
   for name,text in expected.items():(root/name).write_text(text)
   patch=git('diff','--binary','HEAD');command=compact_patch_command(patch)
   self.assertIsNotNone(command);self.assertLess(len(command),len(patch_command(patch)))
   git('reset','--hard','HEAD')
   subprocess.run(['bash','-c',command],cwd=root,check=True)
   self.assertEqual(git('diff','--binary','HEAD'),patch)
   for name,text in expected.items():self.assertEqual((root/name).read_bytes(),text.encode())

 def test_unsupported_and_malformed_patches_keep_original_fallback(self):
  for patch in ['diff --git a/a b/a\nnew file mode 100644\n',
                'diff --git a/a b/a\nBinary files a/a and b/a differ\n',
                'diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,2 +1 @@\n-old\n+new\n',
                'diff --git a/a b/a\n--- a/a\n+++ b/../a\n@@ -1 +1 @@\n-old\n+new\n']:
   self.assertIsNone(compact_patch_command(patch))

 def test_generated_candidate_still_requires_exact_replay(self):
  context=''.join(' context '+str(i)+' x'*30+'\n' for i in range(6))
  patch='diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,7 +1,7 @@\n'+context+'-old\n+new\n'
  compact=compact_patch_command(patch);self.assertIsNotNone(compact)
  seen=[]
  def replay(command):
   seen.append(command)
   return {'returncode':0,'patch':'wrong' if command==compact else patch}
  result=accept_success({'instance_id':'fixture','base_commit':'base'},
      {'resolved':True,'arm':'control','model_patch':patch},{},replay)
  self.assertEqual(seen,[compact,patch_command(patch)])
  self.assertEqual(result['command'],patch_command(patch))
  self.assertFalse(result['replay_trials'][0]['matches_successful_patch'])

 def test_literal_blocks_preserve_backslashes_and_quote_delimiters(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory)
   def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True,stderr=subprocess.DEVNULL)
   git('init');git('config','user.email','fixture@example.invalid');git('config','user.name','Fixture')
   original=''.join('stable context '+str(i)+' x'*30+'\n' for i in range(30))
   p=root/'source.txt';p.write_text(original);git('add','.');git('commit','-m','base')
   for block in ['literal backslash \\n and \\t\n', 'triple double """\n', "triple single ''' and triple double \"\"\"\n"]:
    p.write_text(original.replace('stable context 15',block+'stable context 15'))
    patch=git('diff','--binary','HEAD');command=compact_patch_command(patch);self.assertIsNotNone(command)
    expected=p.read_bytes();git('reset','--hard','HEAD')
    subprocess.run(['bash','-c',command],cwd=root,check=True)
    self.assertEqual(p.read_bytes(),expected);self.assertEqual(git('diff','--binary','HEAD'),patch)
    git('reset','--hard','HEAD')


if __name__=='__main__':unittest.main()
