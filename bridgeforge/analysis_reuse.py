"""Opt-in, invocation-local reuse of pure parsed facts, never qualification evidence.

The byte budget covers serialized payloads; Python container overhead and active
caller objects are additional. No files are read or written by this cache. Pickle
is only used for internally produced objects, never for external cache records.
Scopes belong to one synchronous coordinator, not concurrent worker threads.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import pickle
from typing import Callable, Iterator, TypeVar

T = TypeVar("T")
_active: ContextVar["ParseReuse | None"] = ContextVar("parse_reuse", default=None)


class ParseReuse:
    """Explicit LRU limits; every hit reconstructs an independent caller object."""

    def __init__(self, *, max_entries: int, max_payload_bytes: int) -> None:
        if max_entries <= 0 or max_payload_bytes <= 0:
            raise ValueError("parse reuse limits must be positive")
        self.max_entries = max_entries
        self.max_payload_bytes = max_payload_bytes
        self._entries: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self.payload_bytes = 0
        self.hits = self.misses = self.evictions = self.oversized = 0

    def facts(self, extractor: str, content: bytes, produce: Callable[[], T]) -> T:
        key = (extractor, sha256(content).hexdigest())
        payload = self._entries.get(key)
        if payload is not None:
            self.hits += 1
            self._entries.move_to_end(key)
            return pickle.loads(payload)
        self.misses += 1
        value = produce()  # Exceptions propagate and are never stored.
        payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        if len(payload) > self.max_payload_bytes:
            self.oversized += 1
            return value
        while self._entries and (len(self._entries) >= self.max_entries
                                 or self.payload_bytes + len(payload) > self.max_payload_bytes):
            _, removed = self._entries.popitem(last=False)
            self.payload_bytes -= len(removed)
            self.evictions += 1
        self._entries[key] = payload
        self.payload_bytes += len(payload)
        return value

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "evictions": self.evictions,
                "oversized": self.oversized, "entries": len(self._entries),
                "payload_bytes": self.payload_bytes, "max_entries": self.max_entries,
                "max_payload_bytes": self.max_payload_bytes}


@contextmanager
def reuse_parses(*, max_entries: int, max_payload_bytes: int) -> Iterator[ParseReuse]:
    """Start a fresh bounded scope; restore an enclosing scope even on failure."""
    cache = ParseReuse(max_entries=max_entries, max_payload_bytes=max_payload_bytes)
    token = _active.set(cache)
    try:
        yield cache
    finally:
        _active.reset(token)


def parsed_facts(extractor: str, content: bytes | Callable[[], bytes], produce: Callable[[], T]) -> T:
    cache = _active.get()
    if cache is None:
        return produce()
    return cache.facts(extractor, content() if callable(content) else content, produce)
