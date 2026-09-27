"""Private serialized CPU compiler. Model lifetime is independent of SSH jobs."""
import argparse
import json
import os
import pathlib
import socket
import struct
import tempfile
import time
from remote_compile import MAX_REQUEST, MAX_INDEX, MAX_PAYLOAD, MAGIC, owned_config, transfer, validate_wire
from recover_socket import recover


def handle(client, config, compiler):
    client.settimeout(540)
    with client.makefile('rb') as source:
        raw = source.read(MAX_REQUEST + 1)
    wire = validate_wire(raw, config['model_revision'])
    # Both state and output are daemon-owned; the request cannot choose a path.
    with tempfile.TemporaryDirectory(prefix='resident-', dir=config['state']) as temporary:
        output = pathlib.Path(temporary) / 'payload'
        started = time.perf_counter()
        compiler.compile(wire['request'], output, wire['identity'], wire['key'])
        prepared = time.perf_counter()
        with (output / 'index.json').open('rb') as index, (output / 'compact.pack').open('rb') as payload:
            sizes = [os.fstat(f.fileno()).st_size for f in (index, payload)]
            if not 0 < sizes[0] <= MAX_INDEX or not 0 < sizes[1] <= MAX_PAYLOAD:
                raise ValueError('compiler artifact exceeds limit')
            with client.makefile('wb') as destination:
                destination.write(MAGIC + struct.pack('!QQ', *sizes))
                transfer(index, destination, sizes[0])
                transfer(payload, destination, sizes[1])
        return {'event': 'prepared', 'compile_seconds': round(prepared - started, 6),
                'response_seconds': round(time.perf_counter() - prepared, 6), 'payload_bytes': sizes[1],
                'computation': {k:v for k,v in getattr(compiler, 'last_metrics', {}).items()
                                if k in ('tokens', 'reused_prefix_tokens', 'evaluated_tokens',
                                         'compute_dtype', 'input_seconds', 'forward_seconds',
                                         'export_seconds', 'publish_seconds')}}


def serve(config, path, compiler):
    pathlib.Path(config['state']).mkdir(mode=0o700, parents=True, exist_ok=True)
    recover(path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        previous = os.umask(0o177)
        try:
            server.bind(path)
        finally:
            os.umask(previous)
        inode = os.lstat(path).st_ino
        server.listen(4)
        print(json.dumps({'event': 'ready'}), flush=True)
        try:
            while True:
                client, _ = server.accept()
                with client:
                    try:
                        _, uid, _ = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                        if uid != os.geteuid():
                            raise PermissionError('compiler peer rejected')
                        report = handle(client, config, compiler)
                    except Exception as error:
                        # Never log selected contents, credentials, or model outputs.
                        report = {'event': 'failed', 'error_type': type(error).__name__}
                    print(json.dumps(report), flush=True)
        finally:
            if os.path.exists(path) and os.lstat(path).st_ino == inode:
                os.unlink(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--socket', required=True)
    a = p.parse_args()
    config = owned_config(a.config)
    os.environ['AIMEE_NATIVE_LIBRARY'] = config['library']
    os.environ['HF_HUB_OFFLINE'] = '1'
    from gemma_compile import GemmaCompiler
    started = time.perf_counter()
    compiler = GemmaCompiler(config['model'], config.get('max_memory_tokens', 1024), config.get('threads', 12), config.get('reuse_library'), config.get('compute_dtype','bfloat16'))
    compiler.load()
    print(json.dumps({'event': 'model_loaded', 'seconds': round(time.perf_counter() - started, 6)}), flush=True)
    serve(config, a.socket, compiler)


if __name__ == '__main__':
    main()
