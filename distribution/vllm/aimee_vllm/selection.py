"""Thin local selection RPC; Aimee's reader owns selection and approval."""
import asyncio
import json

async def select(path, body):
    messages=body.get('messages',[])
    query=next((m.get('content') for m in reversed(messages) if m.get('role')=='user'),None)
    if query is None:query=body.get('prompt')
    if not isinstance(query,str) or not query:raise ValueError('text query required')
    reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(path),5)
    try:
        writer.write(json.dumps({'query':query}).encode()+b'\n');await writer.drain()
        result=json.loads(await asyncio.wait_for(reader.readline(),1320))
        if set(result)!={'publication','catalog_digest'} or (result['publication'] is not None and not isinstance(result['publication'],str)):
            raise RuntimeError('selection unavailable')
        return result
    finally:
        writer.close();await writer.wait_closed()
