"""Real subprocess/Unix-socket lifecycle tests; synthetic publication authority."""
import asyncio, importlib.util, json, os, pathlib, sys, tempfile, unittest
spec=importlib.util.spec_from_file_location('follow_native',pathlib.Path(__file__).with_name('follow_native.py'))
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)

class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_preparation_retries_unchanged_view_and_feed_loss_stops_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'config.json').write_text('{}')
            sock=str(root/'control.sock');log=root/'operations'
            server=root/'server.py'
            server.write_text('''import asyncio,json,os,sys,pathlib
root=pathlib.Path(sys.argv[1]);(root/'pid').write_text(str(os.getpid()))
async def handle(r,w):
 q=json.loads(await r.readline())
 with (root/'operations').open('a') as f:f.write(q['op']+'\\n')
 w.write(json.dumps({'state':'active' if q['op']=='refresh' else 'withdrawn','generation':1}).encode()+b'\\n');await w.drain();w.close();await w.wait_closed()
async def main():
 s=await asyncio.start_unix_server(handle,path=str(root/'control.sock'))
 async with s:await s.serve_forever()
asyncio.run(main())
''')
            compiler=root/'compiler.py'
            compiler.write_text('''import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);count=root/'count';n=int(count.read_text())+1 if count.exists() else 1;count.write_text(str(n))
if n==1:sys.exit(1)
print(json.dumps({'authorized_view':'view','recipient':'fixture','root':str(root/'bank'),'model':'fixture','key':'fixture','records':[{'namespace':'fixture','id':'1','revision':'1'}]}))
''')
            follower=root/'follower.py'
            follower.write_text('''import json,pathlib,sys,time
root=pathlib.Path(sys.argv[1]);print(json.dumps({'state':'installed','view':'view'}),flush=True)
for _ in range(100):
 time.sleep(.05)
 print(json.dumps({'state':'unchanged','view':'view'}),flush=True)
 if (root/'operations').exists() and 'refresh' in (root/'operations').read_text():break
''')
            serving=root/'serving.json';serving.write_text(json.dumps({'control_socket':sock,'start_paused':True,'model':str(root),'catalog':str(root/'catalog.json'),'recipient':'fixture'}))
            config={'serving_config':str(serving),'server':[sys.executable,str(server),str(root)],'follower':[sys.executable,str(follower),str(root)],'preparations':{'alpha':[sys.executable,str(compiler),str(root)]}}
            with self.assertRaisesRegex(RuntimeError,'stream ended'):
                await asyncio.wait_for(service.follow(config),15)
            self.assertFalse(pathlib.Path(sock).exists(),'owned socket must not obstruct restart')
            self.assertEqual((root/'count').read_text(),'2')
            self.assertIn('refresh',log.read_text())
            self.assertEqual(json.loads((root/'catalog.json').read_text())['recipient'],'fixture')
            with self.assertRaises(ProcessLookupError):os.kill(int((root/'pid').read_text()),0)

    async def test_busy_feed_does_not_starve_recovery_health_check(self):
        stream=asyncio.StreamReader();stream.feed_data(b'{}\n'*1000)
        checks=[]
        async def control(path,op):checks.append(op);return {'state':'restart_required'}
        from unittest.mock import patch
        with patch.object(service,'control',control):
            with self.assertRaisesRegex(RuntimeError,'recovery required'):
                async for _ in service.events(stream,'fixture'):
                    await asyncio.sleep(.01)
        self.assertEqual(checks,['status'])
