"""Bounded, per-process cache for directory totals; rows and audit records are never cached."""
from collections import OrderedDict
from collections.abc import Hashable
from threading import Lock
from time import monotonic


class EmployeeCountCache:
    def __init__(self, ttl: float = 60, max_entries: int = 512):
        self.ttl = ttl
        self.max_entries = max_entries
        self._entries: OrderedDict[Hashable, tuple[float, int]] = OrderedDict()
        self._generation = 0
        self._lock = Lock()

    def get(self, key: Hashable) -> tuple[int | None, int]:
        """Return the total (None on a miss) and an invalidation generation for a later put."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                expires, total = entry
                if monotonic() < expires:
                    self._entries.move_to_end(key)
                    return total, self._generation
                del self._entries[key]
            return None, self._generation

    def put(self, key: Hashable, total: int, generation: int) -> None:
        with self._lock:
            # An older in-flight search must not repopulate the cache after a hire commits.
            if generation != self._generation:
                return
            self._entries[key] = (monotonic() + self.ttl, total)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def invalidate(self) -> None:
        """Call after a successful commit that changes directory membership or searchable fields."""
        with self._lock:
            self._generation += 1
            self._entries.clear()


employee_count_cache = EmployeeCountCache()
