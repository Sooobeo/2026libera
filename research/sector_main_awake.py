"""Main-only duration adapter for reviewed same-thread temporary wakefulness."""
from datetime import timedelta

from sector_continuation_awake import CoordinatorAwake as BaseAwake, now, FLAGS, CLEAR


class MainCoordinatorAwake(BaseAwake):
    def __init__(self, emit, *, api=None):
        super().__init__(emit, api=api)
        self.expires = now() + timedelta(seconds=10 * 4500 + 1800)
