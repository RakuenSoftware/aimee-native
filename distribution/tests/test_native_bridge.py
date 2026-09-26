"""Exercise Aimee's actual C transport against the private delivery service.
Identity grants here are explicit fixtures, not a live production authorization.
"""
import argparse,datetime,hashlib,json,os,pathlib,subprocess,tempfile,time,unittest

p=argparse.ArgumentParser();p.add_argument('--aimee',required=True);p.add_argument('--delivery',required=True)
a,rest=p.parse_known_args()

class Bridge(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='aimee-bridge-');cls.root=pathlib.Path(cls.temp.name)
  cls.socket=cls.root/'delivery.sock'
  c=cls.root/'probe.c'
  c.write_text('''#define _GNU_SOURCE
#include "server_native_delivery.h"
int server_conn_io_write_all(int fd,const void *p,int n){return (int)write(fd,p,(size_t)n);}
int main(int argc,char **argv){
 if(argc!=4 || !server_native_delivery_route(argv[1],argv[2]))return 2;
 int backend_status=0;
 int status=server_native_delivery_forward(1,argv[1],argv[2],argv[3],"",0,&backend_status);
 fprintf(stderr,"%d\\n",backend_status);
 if(status)printf("HTTP/1.1 %d rejected\\r\\n\\r\\n",status);
 return 0;
}
''')
  cls.probe=cls.root/'probe'
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(pathlib.Path(a.aimee)/'src/headers'),str(c),'-o',str(cls.probe)],check=True)
  cls.policy={'version':1,'recipient':'alice','peer_uid':os.geteuid(),'namespace':'personal','base_view':'a'*64,'valid_until':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat(),'active':True,'records':[]}
  cls.release=cls.root/'release.json';cls.write_policy()
  bindings={'schema':1,'bindings':[{'principal':'webuser:alice','release_policy':str(cls.release),'publisher_uid':os.geteuid(),'preparer':{'Binary':'/not-used','Template':'/not-used','Profile':{'schema':1,'recipient':'alice','model':'test-profile','model_config_sha256':'b'*64}}}]}
  file=cls.root/'bindings.json';file.write_text(json.dumps(bindings));file.chmod(0o600)
  cls.service=subprocess.Popen([a.delivery,'--socket',str(cls.socket),'--bindings',str(file),'--frontend-uid',str(os.geteuid())],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  for _ in range(100):
   if cls.socket.exists():break
   if cls.service.poll() is not None:raise RuntimeError(cls.service.stderr.read().decode())
   time.sleep(.02)
  else:raise RuntimeError('listener did not start')
 @classmethod
 def write_policy(cls):
  tmp=cls.root/'release.tmp';tmp.write_text(json.dumps(cls.policy));tmp.chmod(0o600);tmp.replace(cls.release)
 @classmethod
 def tearDownClass(cls):
  cls.service.terminate();cls.service.wait(timeout=5);cls.service.stderr.close();cls.temp.cleanup()
 def run_request(self,principal='webuser:alice',path='/v1/native/bootstrap',method='GET'):
  return subprocess.run([str(self.probe),method,path,principal],env=dict(os.environ,AIMEE_NATIVE_SOCKET=str(self.socket)),capture_output=True,check=False)
 def test_current_binding_and_withdrawal(self):
  self.policy['active']=True;self.write_policy()
  result=self.run_request();self.assertEqual(result.returncode,0);self.assertIn(b'200 OK',result.stdout);self.assertEqual(result.stderr,b'200\n');self.assertIn(b'"recipient":"alice"',result.stdout)
  self.policy['active']=False;self.write_policy()
  self.assertIn(b'403',self.run_request().stdout)
  self.policy['active']=True;self.write_policy()
  self.assertIn(b'200 OK',self.run_request().stdout)
 def test_unbound_and_empty_identity(self):
  for principal in ('webuser:bob',''):
   self.assertIn(b'403',self.run_request(principal).stdout)
 def test_route_whitelist(self):
  for path in ('/v1/native/bootstrap/extra','/v1/native/leases/../compact.pack','/v1/native/bootstrap\r\nX: y'):
   self.assertEqual(self.run_request(path=path).returncode,2)
 def test_private_socket_required(self):
  self.socket.chmod(0o666)
  try:self.assertIn(b'503',self.run_request().stdout)
  finally:self.socket.chmod(0o600)

if __name__=='__main__':unittest.main(argv=['test_native_bridge.py']+rest)
