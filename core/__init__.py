"""Core headless service internals (spec §3).

The public contract is :mod:`core.types`. The HTTP boundary lives in
:mod:`api.server`; nothing in here may import FastAPI.
"""
