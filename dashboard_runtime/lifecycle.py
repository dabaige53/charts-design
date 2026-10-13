"""Bounded idle lifetime shared by local transports."""
from contextlib import contextmanager
from functools import wraps
from threading import RLock
from time import monotonic
from math import isfinite

DEFAULT_IDLE_TIMEOUT = 60


class IdleLifetime:
    def __init__(self, timeout: float=DEFAULT_IDLE_TIMEOUT, clock=monotonic):
        if not isfinite(timeout) or timeout <= 0:
            raise ValueError('Idle timeout must be positive')
        self.timeout, self.clock = timeout, clock
        self.last_activity, self.active = clock(), 0
        self.lock = RLock()

    @contextmanager
    def activity(self):
        with self.lock:
            self.active += 1
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1
                self.last_activity = self.clock()

    def expired(self):
        with self.lock:
            return not self.active and self.clock() - self.last_activity >= self.timeout

    def track(self, function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            with self.activity():
                return await function(*args, **kwargs)
        return wrapped
