"""Read-only canary bootstrap authorization; credentials never enter reports."""
import argparse
import http.client
import json
import pathlib
import socket
import ssl
import urllib.parse

p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--recipient',required=True);p.add_argument('--output',required=True);a=p.parse_args()
config=json.loads(pathlib.Path(a.config).read_text())
url=urllib.parse.urlsplit(config['endpoint'])
if url.scheme!='https' or not url.hostname:raise ValueError('HTTPS authority required')
token=pathlib.Path(config['token_file']).read_text().strip()
report={'status':'incomplete','scope':'Read-only live bootstrap authority with enrolled client; not a lease/GPU isolation test','results':{}}

def request(label,credential,identity=True):
    context=ssl.create_default_context(cafile=config['ca_file'])
    if identity:context.load_cert_chain(config['client_identity'])
    address=config.get('connect_address')
    target=(url.hostname,url.port or 443)
    if address:
        host,port=address.rsplit(':',1);target=(host.strip('[]'),int(port))
    connection=http.client.HTTPSConnection(url.hostname,url.port or 443,context=context,timeout=20)
    try:
        connection.sock=context.wrap_socket(socket.create_connection(target,timeout=20),server_hostname=url.hostname)
        headers={} if credential is None else {'Authorization':'Bearer '+credential}
        connection.request('GET',url.path.rstrip('/')+'/v1/native/bootstrap',headers=headers)
        response=connection.getresponse();body=response.read(65537)
        result={'status':response.status}
        if label=='enrolled':
            data=json.loads(body)
            result['profile_matches']=data.get('schema')==1 and data.get('recipient')==a.recipient
        return result
    except ssl.SSLError as error:
        return {'tls_error':error.reason}
    finally:connection.close()

try:
    for label,credential,identity in [('enrolled',token,True),('invalid_bearer','invalid-release-validation-token',True),('missing_bearer',None,True),('missing_client_certificate',token,False)]:
        result=request(label,credential,identity);report['results'][label]=result
        if label=='enrolled':passed=result.get('status')==200 and result.get('profile_matches') is True
        elif label=='missing_client_certificate':passed=result.get('tls_error') in ('TLSV13_ALERT_CERTIFICATE_REQUIRED','SSLV3_ALERT_BAD_CERTIFICATE') or result.get('status') in (401,403)
        else:passed=result.get('status')==401
        result['passed']=passed
        if not passed:raise RuntimeError('authority case failed: '+label)
    report['status']='passed'
except BaseException:
    report['status']='failed'
    raise
finally:pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
