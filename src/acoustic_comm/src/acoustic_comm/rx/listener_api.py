from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable, Optional, Any

from .realtime_listener_working import (
    STOP_CMD,
    RealtimeListenerConfig,
    listen_forever,
)
from ..protocol.codebook import cmd_name
from ..protocol.constants import FAST_CONFIG, SLOW_CONFIG


@dataclass
class DetectionEvent:
    valid: bool
    mode: str
    cmd_id: int
    cmd_hex: str
    cmd_name: str
    seq: int
    score_raw: float
    confidence: float
    input_level: float
    source: str = "acoustic_comm"
    is_stop_command: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class RealtimeListener:
    """
    Importable wrapper around listen_forever().

    Design goals:
    - Keep existing realtime listener implementation largely unchanged
    - Keep terminal prints from realtime_listener_working.py unchanged
    - Expose accepted detections as structured callback events
    - Be usable from a ROS 2 node through import
    - Support real external stop()
    """

    def __init__(
        self,
        rt_cfg: Optional[RealtimeListenerConfig] = None,
        input_device: int | None = None,
        print_detection: bool = False,
    ):
        self.rt_cfg = rt_cfg if rt_cfg is not None else RealtimeListenerConfig()
        self.input_device = input_device
        self.print_detection = print_detection

        self._running = False
        self._stop_requested = False

    @property
    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        """
        Request underlying listen_forever() loop to exit.
        """
        self._stop_requested = True

    def run_forever(
        self,
        on_detection: Optional[Callable[[DetectionEvent], None]] = None,
    ) -> None:
        """
        Blocking call. Intended to be run in a separate thread by ROS node.

        Example:
            listener = RealtimeListener(...)
            listener.run_forever(on_detection=callback)
        """
        self._stop_requested = False
        self._running = True

        def _safe_cmd_name(value: int) -> str:
            try:
                return cmd_name(int(value))
            except Exception:
                return f"UNKNOWN_0x{int(value):02X}"

        def _handle_trigger(cmd_id: int, seq: int, meta: dict[str, Any]) -> None:
            if self._stop_requested:
                return

            cmd_id_i = int(cmd_id)
            seq_i = int(seq)

            mode = str(meta.get("mode", "unknown"))
            score = float(meta.get("best_score", 0.0))
            input_level = float(meta.get("input_level", 0.0))
            name = str(meta.get("cmd_name", _safe_cmd_name(cmd_id_i)))
            cmd_hex = f"0x{cmd_id_i:02X}"

            event = DetectionEvent(
                valid=True,
                mode=mode,
                cmd_id=cmd_id_i,
                cmd_hex=cmd_hex,
                cmd_name=name,
                seq=seq_i,
                score_raw=score,
                confidence=score,
                input_level=input_level,
                source="acoustic_comm",
                is_stop_command=(cmd_id_i == STOP_CMD),
                note="",
            )

            if self.print_detection:
                print(
                    "[listener_api] accepted: "
                    f"mode={event.mode} "
                    f"cmd={event.cmd_hex} "
                    f"name={event.cmd_name} "
                    f"seq={event.seq} "
                    f"score={event.score_raw:.4f}"
                )

            if on_detection is not None:
                on_detection(event)

        try:
            listen_forever(
                fast_cfg=FAST_CONFIG,
                slow_cfg=SLOW_CONFIG,
                rt_cfg=self.rt_cfg,
                device=self.input_device,
                on_trigger=_handle_trigger,
                should_stop=lambda: self._stop_requested,
            )
        finally:
            self._running = False