"""Isolated TLS release test origin; never a production publication authority."""
import argparse,functools,http.server,ssl
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--cert',required=True);p.add_argument('--key',required=True);p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=8444);a=p.parse_args()
server=http.server.ThreadingHTTPServer((a.host,a.port),functools.partial(http.server.SimpleHTTPRequestHandler,directory=a.root))
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(a.cert,a.key)
server.socket=context.wrap_socket(server.socket,server_side=True)
server.serve_forever()
