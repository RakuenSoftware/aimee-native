"""Frozen consumption instructions for the matching BF16 serving profile.

Explicitly permit named-entity resolution without asserting new identity facts.
This is separate from historical research prompts, whose failures are retained.
"""
from campaign import SYSTEM as BASE_SYSTEM

PROFILE = 'complete-hybrid-entity-resolution-system-v1'
SYSTEM = BASE_SYSTEM + ' Resolve named entities and follow the recorded connections even when the question uses a different descriptive noun; do not invent an identity or connection.'
