"""Six-stage same-main-thread awake ownership; inherited reviewed API behavior."""
from datetime import timedelta
from sector_continuation_awake import CoordinatorAwake as ReviewedCoordinatorAwake, FLAGS, CLEAR, NativeAPI, now

MAX_OPERATIONAL_SECONDS = 6 * (4500 + 1800) + 1800


class CoordinatorAwake(ReviewedCoordinatorAwake):
    def __init__(self, emit, *, api=None):
        super().__init__(emit, api=api)
        self.expires = now() + timedelta(seconds=MAX_OPERATIONAL_SECONDS)
