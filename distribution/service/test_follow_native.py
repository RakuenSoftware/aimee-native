import asyncio,importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('follow_native',pathlib.Path(__file__).with_name('follow_native.py'));service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
class FollowTests(unittest.IsolatedAsyncioTestCase):
    async def test_publisher_stream_end_stops_both_owned_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);c=root/'serving.json';c.write_text(json.dumps({'control_socket':'fixture','start_paused':True}))
            class Stream:
                async def readline(self):return b""
            class Child:
                returncode=None
                stdout=Stream()
            server,follower=Child(),Child();created=[server,follower];stopped=[];ops=[]
            async def spawn(*args,**kw):return created.pop(0)
            async def stop(child):stopped.append(child)
            async def control(path,op):ops.append(op);return {'state':'withdrawn'}
            with patch.object(asyncio,'create_subprocess_exec',spawn),patch.object(service,'stop',stop),patch.object(service,'control',control):
                with self.assertRaises(RuntimeError):await service.follow({'serving_config':str(c),'server':['fixture-server'],'follower':['fixture-follower'],'preparations':{}})
            self.assertEqual(ops,['withdraw']);self.assertEqual(stopped,[server,follower])
    async def test_requires_closed_initial_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=pathlib.Path(tmp)/'serving.json';c.write_text(json.dumps({'control_socket':'fixture'}))
            with self.assertRaises(RuntimeError):await service.follow({'serving_config':str(c)})
    async def test_recovery_restarts_whole_authority_session(self):
        calls=[]
        async def fail(config):calls.append(1);raise RuntimeError('restart required')
        async def immediate(*args):pass
        with patch.object(service,'follow',fail),patch.object(asyncio,'sleep',immediate):
            with self.assertRaises(RuntimeError):await service.main({'restart_limit':2})
        self.assertEqual(len(calls),3)
    def test_catalog_atomic_install_uses_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/'catalog.json';service.publish(p,{'publications':{}})
            self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertEqual(json.loads(p.read_text()),{'publications':{}})
if __name__=='__main__':unittest.main()
