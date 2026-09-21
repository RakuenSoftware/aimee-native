"""Opt-in synchronized wall timings for the serial research runtime."""
from contextlib import contextmanager
import time
import torch


def synchronize():
    if torch.cuda.is_available():
        for device in range(torch.cuda.device_count()):
            torch.cuda.synchronize(device)


class Profile:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.events = []

    @contextmanager
    def span(self, name):
        if not self.enabled:
            yield
            return
        synchronize()
        start = time.perf_counter()
        try:
            yield
        finally:
            synchronize()
            self.events.append({'stage': name, 'start': start, 'seconds': time.perf_counter()-start})


class TokenClock:
    """Generation streamer that records availability, without decoding text."""
    def __init__(self):
        self.prompt = True
        self.times = []

    def put(self, value):
        if self.prompt:
            self.prompt = False
        else:
            self.times.append(time.perf_counter())

    def end(self):
        pass
