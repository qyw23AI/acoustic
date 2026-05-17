from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import time
from typing import Sequence


@dataclass(frozen=True)
class VoteResult:
    """
    Result of majority vote over decoded (cmd, seq) pairs.
    """
    cmd: int
    seq: int
    count: int
    total: int


def majority_vote(
    decoded: Sequence[tuple[int, int]],
    min_count: int = 1,
) -> VoteResult | None:
    """
    Majority vote over decoded (cmd, seq) items.

    Notes
    -----
    - In no-seq modes, decoded items are typically (cmd, 0)
    - In legacy mode, decoded items are typically (cmd, seq)
    """
    if min_count <= 0:
        raise ValueError(f"min_count must be positive, got {min_count}")

    if not decoded:
        return None

    winner, count = Counter(decoded).most_common(1)[0]
    if count < min_count:
        return None

    cmd, seq = winner
    return VoteResult(
        cmd=int(cmd),
        seq=int(seq),
        count=int(count),
        total=len(decoded),
    )


@dataclass
class TriggerGuard:
    """
    Guard against repeated or too-frequent triggers.

    Features
    --------
    1. Cooldown: reject triggers that arrive too soon after the last accepted one.
    2. Replay protection within a time window, instead of "remember forever".
    3. Can work in two modes:
       - no-seq mode: replay key is cmd
       - seq mode: replay key is (cmd, seq)
    """

    cooldown_s: float = 1.0
    replay_window_s: float = 2.0
    max_seen: int = 64
    use_seq_for_replay: bool = False

    _last_accept_time: float = field(default=float("-inf"), init=False, repr=False)
    _seen_time: dict[tuple[int, ...], float] = field(default_factory=dict, init=False, repr=False)

    def reset(self) -> None:
        """
        Clear cooldown and replay history.
        """
        self._last_accept_time = float("-inf")
        self._seen_time.clear()

    def seen_count(self) -> int:
        """
        Return how many recent replay keys are remembered.
        """
        return len(self._seen_time)

    def _prune(self, now: float) -> None:
        """
        Remove expired replay keys and keep memory bounded.
        """
        if self.replay_window_s > 0:
            expired = [
                key for key, ts in self._seen_time.items()
                if now - ts >= self.replay_window_s
            ]
            for key in expired:
                self._seen_time.pop(key, None)

        while len(self._seen_time) > self.max_seen:
            oldest_key = min(self._seen_time, key=self._seen_time.get)
            self._seen_time.pop(oldest_key, None)

    def _make_key(self, cmd: int, seq: int, use_seq: bool) -> tuple[int, ...]:
        cmd = int(cmd) & 0xFF
        seq = int(seq) & 0xFF
        return (cmd, seq) if use_seq else (cmd,)

    def check_and_mark(
        self,
        cmd: int,
        seq: int = 0,
        now: float | None = None,
        use_seq: bool | None = None,
    ) -> bool:
        """
        Return True if this trigger should be accepted, and mark it as accepted.

        Rejection happens when:
        - still in cooldown window
        - replay key has already been accepted recently

        Parameters
        ----------
        cmd : int
            Command id.
        seq : int
            Sequence id. Ignored when replay key does not use seq.
        now : float | None
            Optional monotonic timestamp override.
        use_seq : bool | None
            Whether replay key should include seq.
            - None: use self.use_seq_for_replay
            - False: replay key is (cmd,)
            - True: replay key is (cmd, seq)
        """
        if now is None:
            now = time.monotonic()

        if use_seq is None:
            use_seq = self.use_seq_for_replay

        # cooldown protection
        if now - self._last_accept_time < self.cooldown_s:
            return False

        self._prune(now)
        key = self._make_key(cmd, seq, use_seq=use_seq)

        # replay protection within a time window
        if self.replay_window_s > 0 and key in self._seen_time:
            return False

        # accept and remember
        self._last_accept_time = now
        if self.replay_window_s > 0:
            self._seen_time[key] = now
            self._prune(now)

        return True