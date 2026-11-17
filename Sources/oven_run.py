"""State of one bake: collects readings and decides when the hold time is over.
No GUI code in here, so it can be tested without PyQt.
"""
from datetime import timedelta

WARM_UP = "Warm-Up"
HEATED = "Heated"

class OvenRun:
    def __init__(self, temp_target: int, hold_seconds: int):
        self.temp_target = temp_target
        self.hold_seconds = hold_seconds
        self.times = []
        self.temps = []
        self.states = []
        self.trigger_time = None   # first reading that reached temp_target
        self.stop_time = None      # trigger_time + hold_seconds
    @property
    def triggered(self) -> bool:
        return self.trigger_time is not None
    def add_reading(self, now, temp) -> str:
        """Store one reading and return its state (Warm-Up / Heated).
        The reading that reaches the target is still Warm-Up; the hold
        time starts counting from it.
        """
        state = HEATED if self.triggered else WARM_UP
        self.times.append(now)
        self.temps.append(temp)
        self.states.append(state)
        if not self.triggered and temp >= self.temp_target:
            self.trigger_time = now
            self.stop_time = now + timedelta(seconds=self.hold_seconds)
        return state
    def minutes_left(self, now):
        """Whole minutes left in the hold, or None if the target was not reached yet."""
        if self.stop_time is None:
            return None
        return int((self.stop_time - now).total_seconds() / 60)
    def is_finished(self, now) -> bool:
        return self.stop_time is not None and now >= self.stop_time