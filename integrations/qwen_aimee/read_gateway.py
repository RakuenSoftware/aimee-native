#!/usr/bin/env python3
"""Separate credential-bearing, read-only Aimee gateway for the model runtime.
Only POST /search with query/limit is accepted. No generic proxy or write route.
"""
import argparse
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
from aimee_client import AimeeClient, AimeeUnixClient
from local_image import AimeeImageClient


def main():
    p=argparse.ArgumentParser();p.add_argument('--socket',required=True);p.add_argument('--config');p.add_argument('--ca');p.add_argument('--cert');p.add_argument('--key');p.add_argument('--upstream-unix')
    p.add_argument('--image-reader',required=True);p.add_argument('--memory-image',required=True)
    p.add_argument('--authorization',required=True);p.add_argument('--authority-key',required=True)
    p.add_argument('--subject',required=True);p.add_argument('--policy-epoch',required=True)
    args=p.parse_args()
    if args.upstream_unix:
        if any((args.config,args.ca,args.cert,args.key)):p.error('choose exactly one upstream transport')
        client=AimeeUnixClient(args.upstream_unix)
    else:
        if not all((args.config,args.ca,args.cert,args.key)):p.error('HTTPS requires config, CA and client identity')
        client=AimeeClient(args.config,args.ca,cert_file=args.cert,key_file=args.key,keepalive=True)
    guard=AimeeImageClient(args.image_reader,args.memory_image,authorization=args.authorization,
                           authority_key=args.authority_key,subject=args.subject,policy_epoch=args.policy_epoch)
    guard.begin_request()
    binding=guard.authorization_id
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,data):
            raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            if self.path not in ('/search','/identity'):self.reply(403,{'error':'read-only gateway'});return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:raise ValueError()
                body=json.loads(self.rfile.read(size))
                guard.begin_request()
                if guard.authorization_id!=binding:raise RuntimeError('authorization changed')
                if self.path=='/identity':
                    if body!={}:raise ValueError()
                    self.reply(200,{'authorization':binding});return
                if not isinstance(body,dict) or set(body)!={'query','limit','authorization'}:raise ValueError()
                if body['authorization']!=binding:
                    self.reply(403,{'error':'authorization mismatch'});return
                result=client.search(body['query'],body['limit'])
                # No partial redaction: reject the entire result if any field
                # or record exceeds the fixed Aimee authorization.
                guard.authorize_response(result)
            except ValueError:self.reply(400,{'error':'invalid read request'});return
            except Exception:self.reply(403,{'error':'authorized read unavailable'});return
            self.reply(200,result)
    path=Path(args.socket)
    if path.exists():raise RuntimeError('socket already exists; remove only after stopping its owner')
    with socketserver.UnixStreamServer(str(path),Handler) as server:
        os.chmod(path,0o660)
        try:server.serve_forever()
        finally:client.close();guard.close();path.unlink(missing_ok=True)

if __name__=='__main__':main()
