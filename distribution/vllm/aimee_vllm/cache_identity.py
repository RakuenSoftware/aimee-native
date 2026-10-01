"""Trusted vLLM text-cache namespace for a native publication revision."""
import hashlib
import json


def cache_salt(recipient, catalog_digest, publication):
    # Text K/V depends on native attention in earlier layers. A cache hit is
    # valid only for the same recipient, complete catalogue revision and bank.
    identity = json.dumps([recipient, catalog_digest, publication], separators=(',', ':'))
    return hashlib.sha256(identity.encode()).hexdigest()
