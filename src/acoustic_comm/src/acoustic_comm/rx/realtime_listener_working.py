from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Any

import numpy as np
from scipy.signal import resample_poly

from ..dsp.chirp_sync import find_topk_chirp_peaks, make_chirp_template
from ..dsp.fsk import decode_bits_from
from ..io.audio_device import open_input_stream
from ..io.wav import write_wav
from ..protocol.codebook import cmd_name, is_fast_cmd, is_slow_cmd
from ..protocol.constants import AcousticConfig, FAST_CONFIG, SLOW_CONFIG
from ..protocol.frame import bits_to_bytes, check_frame


STOP_CMD = 0xC6


@dataclass(frozen=True)
class RealtimeListenerConfig:
    """
    Runtime-only parameters for realtime listening.
    New policy:
    - Fast / ordinary Slow: one valid frame is enough
    - STOP: require two valid frames
    - after accept: clear ring and suppress for a short window
    """
    hop_s: float = 0.02
    ring_s: float = 3.0
    min_gap_s: float = 0.20
    search_topk: int = 8

    # separate thresholds for fast / slow chirp search
    fast_chirp_thresh: float = 0.10
    slow_chirp_thresh: float = 0.10

    # accept policy
    fast_accept_min: int = 1
    slow_accept_min: int = 1
    stop_accept_min: int = 2

    # refine chirp locally around coarse peak
    refine_window_s: float = 0.01
    refine_step_samples: int = 2

    # try several bit-phase offsets after chirp
    phase_div: int = 8

    # debug / capture
    debug_every_s: float = 0.5
    verbose_debug: bool = False
    save_debug_ring: bool = False
    debug_ring_path: str = "debug_ring.wav"

    # accepted-trigger capture
    save_capture: bool = False
    capture_dir: str = "."
    capture_prefix: str = "realtime_capture"

    # post-accept behavior
    clear_ring_after_accept: bool = True
    fast_post_accept_s: float = 1.25
    slow_post_accept_s: float = 2.0
    stop_post_accept_s: float = 3.0

    # fast packet structure prior: 2 repeats, second chirp should appear
    # around first_abs_peak + expected_repeat_offset_samples(cfg)
    fast_repeat_tol_s: float = 0.05

    # debug aid for clipping
    clip_warn_level: float = 0.90

    fast_accept_score_min: float = 0.20

    startup_warmup_s: float = 0.5

    # microphone/device capture rate; protocol/decode still uses cfg.sr
    input_sr: int | None = None


@dataclass
class ModeScanState:
    """
    Remember how far we have already scanned in absolute sample index.
    This is the key difference from the old listener.
    """
    last_peak_abs: int = -(10**18)


def _resample_block(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """
    Resample one waveform from device sample rate to protocol sample rate.
    """
    x = np.asarray(x, dtype=np.float32)
    if len(x) == 0 or src_sr == dst_sr:
        return x

    g = math.gcd(int(src_sr), int(dst_sr))
    up = int(dst_sr // g)
    down = int(src_sr // g)

    y = resample_poly(x, up=up, down=down)
    return np.asarray(y, dtype=np.float32)


def _update_ring(ring: np.ndarray, block: np.ndarray) -> None:
    n = len(block)
    if n <= 0:
        return
    if n >= len(ring):
        ring[:] = block[-len(ring):]
        return

    ring[:-n] = ring[n:]
    ring[-n:] = block


def _chirp_score_at(x: np.ndarray, tpl: np.ndarray, start_idx: int) -> float:
    """
    Normalized chirp match score in [0, 1]-ish range.
    """
    if start_idx < 0 or start_idx + len(tpl) > len(x):
        return 0.0

    seg = np.asarray(x[start_idx:start_idx + len(tpl)], dtype=np.float32)
    if len(seg) != len(tpl):
        return 0.0

    denom = float(np.linalg.norm(seg) * np.linalg.norm(tpl) + 1e-12)
    if denom <= 1e-12:
        return 0.0

    return float(abs(np.dot(seg, tpl)) / denom)


def _decode_frame_near_peak(
    x: np.ndarray,
    coarse_peak: int,
    cfg: AcousticConfig,
    rt_cfg: RealtimeListenerConfig,
    chirp_tpl: np.ndarray,
) -> dict:
    """
    Around a coarse chirp peak:
    1) refine chirp start locally using normalized chirp score
    2) try several bit-phase offsets
    3) validate frame (CRC if enabled by cfg)
    """
    best_idx = int(coarse_peak)
    best_score = _chirp_score_at(x, chirp_tpl, best_idx)

    search = int(round(rt_cfg.refine_window_s * cfg.sr))
    step = max(1, int(rt_cfg.refine_step_samples))

    for off in range(-search, search + 1, step):
        idx = coarse_peak + off
        sc = _chirp_score_at(x, chirp_tpl, idx)
        if sc > best_score:
            best_score = sc
            best_idx = idx

    payload_start0 = best_idx + cfg.chirp_len
    nbits = cfg.frame_bits
    bit_len = cfg.bit_len

    best_try = {
        "ok": False,
        "reason": "frame_check_failed",
        "peak": int(best_idx),
        "score": float(best_score),
        "payload_start": int(payload_start0),
        "cmd": None,
        "seq": None,
        "frame_bytes": None,
        "phase": None,
    }

    phase_step = max(1, bit_len // max(1, rt_cfg.phase_div))
    for phase in range(0, bit_len, phase_step):
        start_idx = payload_start0 + phase
        bits = decode_bits_from(
            x=x,
            start_idx=start_idx,
            nbits=nbits,
            sr=cfg.sr,
            bit_dur=cfg.bit_dur,
            f0=cfg.f0,
            f1=cfg.f1,
        )
        if bits is None or len(bits) != nbits:
            continue

        frame_bytes = bits_to_bytes(bits, msb_first=cfg.msb_first)
        ok, cmd, seq = check_frame(frame_bytes, cfg)
        item = {
            "ok": bool(ok),
            "reason": None if ok else "frame_check_failed",
            "peak": int(best_idx),
            "score": float(best_score),
            "payload_start": int(start_idx),
            "cmd": int(cmd),
            "seq": int(seq),
            "frame_bytes": frame_bytes,
            "phase": int(phase),
        }
        if ok:
            return item

        best_try = item

    return best_try


def _mode_matches_cmd(mode: str, cmd: int) -> bool:
    if mode == "fast":
        return is_fast_cmd(cmd)
    if mode == "slow":
        return is_slow_cmd(cmd)
    return False


def _required_accept_min(mode: str, cmd: int, rt_cfg: RealtimeListenerConfig) -> int:
    if mode == "fast":
        return rt_cfg.fast_accept_min
    if cmd == STOP_CMD:
        return rt_cfg.stop_accept_min
    return rt_cfg.slow_accept_min


def _post_accept_holdoff_s(mode: str, cmd: int, rt_cfg: RealtimeListenerConfig) -> float:
    if mode == "fast":
        return rt_cfg.fast_post_accept_s
    if cmd == STOP_CMD:
        return rt_cfg.stop_post_accept_s
    return rt_cfg.slow_post_accept_s


def _chirp_thresh_for_mode(mode: str, rt_cfg: RealtimeListenerConfig) -> float:
    return rt_cfg.fast_chirp_thresh if mode == "fast" else rt_cfg.slow_chirp_thresh


def _accept_score_min_for_mode(mode: str, rt_cfg: RealtimeListenerConfig) -> float:
    return rt_cfg.fast_accept_score_min if mode == "fast" else 0.0


def _expected_repeat_offset_samples(cfg: AcousticConfig) -> int:
    """
    For fast:
    repeat offset = one whole frame duration + inter-frame gap
                  = silence_head + chirp + payload + gap
    """
    silence_head_len = getattr(
        cfg,
        "silence_head_len",
        int(round(float(getattr(cfg, "silence_head_s", 0.0)) * cfg.sr)),
    )
    gap_len = getattr(
        cfg,
        "gap_len",
        int(round(float(getattr(cfg, "gap_s", 0.0)) * cfg.sr)),
    )
    payload_len = int(cfg.frame_bits * cfg.bit_len)
    return int(silence_head_len + cfg.chirp_len + payload_len + gap_len)


def _is_expected_fast_repeat(
    first_abs_peak: int,
    second_abs_peak: int,
    cfg: AcousticConfig,
    rt_cfg: RealtimeListenerConfig,
) -> bool:
    expect = _expected_repeat_offset_samples(cfg)
    tol = int(round(rt_cfg.fast_repeat_tol_s * cfg.sr))
    delta = int(second_abs_peak) - int(first_abs_peak)
    return abs(delta - expect) <= tol


def _summarize_ok_frames(mode: str, ok_items: list[dict], rt_cfg: RealtimeListenerConfig) -> dict | None:
    """
    Choose the best decoded cmd/seq among valid frames.
    Fast / ordinary Slow: 1 frame is enough
    STOP: need stronger acceptance
    """
    if not ok_items:
        return None

    stats: dict[tuple[int, int], dict] = {}
    for item in ok_items:
        key = (int(item["cmd"]), int(item["seq"]))
        entry = stats.setdefault(
            key,
            {
                "count": 0,
                "best_score": float("-inf"),
                "best_item": None,
            },
        )
        entry["count"] += 1
        if float(item["score"]) > float(entry["best_score"]):
            entry["best_score"] = float(item["score"])
            entry["best_item"] = item

    best_key, best_entry = max(
        stats.items(),
        key=lambda kv: (int(kv[1]["count"]), float(kv[1]["best_score"])),
    )
    cmd, seq = best_key
    need = _required_accept_min(mode, cmd, rt_cfg)
    if int(best_entry["count"]) < need:
        return None

    return {
        "cmd": int(cmd),
        "seq": int(seq),
        "vote_count": int(best_entry["count"]),
        "best_score": float(best_entry["best_score"]),
        "best_item": best_entry["best_item"],
    }


def _collect_mode_candidate(
    wave: np.ndarray,
    mode: str,
    cfg: AcousticConfig,
    chirp_tpl: np.ndarray,
    rt_cfg: RealtimeListenerConfig,
    ring_start_abs: int,
    state: ModeScanState,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict | None:
    """
    Fast:
    - still allow single-frame accept
    - but only treat a second frame as the same packet if it falls inside
      the expected repeat window after the first frame

    Slow:
    - keep old summarization logic
    """
    peaks = find_topk_chirp_peaks(
        x=wave,
        chirp_tpl=chirp_tpl,
        sr=cfg.sr,
        k=rt_cfg.search_topk,
        min_gap_s=rt_cfg.min_gap_s,
        score_threshold=_chirp_thresh_for_mode(mode, rt_cfg),
        use_abs=True,
    )

    if rt_cfg.verbose_debug:
        top = ", ".join(f"({int(p)}, {float(s):.4f})" for p, s in peaks[:5])
        print(f"[{mode}] peaks={len(peaks)} top=[{top}]")

    if not peaks:
        return None

    max_phase_slack = cfg.bit_len
    frame_need_len = cfg.chirp_len + cfg.frame_bits * cfg.bit_len + max_phase_slack

    frame_results: list[dict] = []
    ok_items: list[dict] = []

    processed_abs_max = state.last_peak_abs

    for peak, raw_score in peaks:
        if should_stop is not None and should_stop():
            print(f"[realtime_listener] stop requested during {mode} candidate scan")
            break

        abs_peak = int(ring_start_abs + peak)

        if abs_peak <= state.last_peak_abs:
            continue

        if peak + frame_need_len > len(wave):
            continue

        processed_abs_max = max(processed_abs_max, abs_peak)

        item = _decode_frame_near_peak(
            x=wave,
            coarse_peak=peak,
            cfg=cfg,
            rt_cfg=rt_cfg,
            chirp_tpl=chirp_tpl,
        )
        item["abs_peak"] = int(abs_peak)
        item["raw_peak_score"] = float(raw_score)
        frame_results.append(item)

        if rt_cfg.verbose_debug:
            print(
                f"[{mode}] abs_peak={abs_peak} raw={raw_score:.4f} "
                f"ok={item['ok']} cmd={item['cmd']} seq={item['seq']} "
                f"score={item['score']:.4f} phase={item['phase']}"
            )

        if item["ok"] and _mode_matches_cmd(mode, int(item["cmd"])):
            ok_items.append(item)

    state.last_peak_abs = processed_abs_max

    if not frame_results:
        return None

    # -------------------------
    # fast: packet-aware pairing
    # -------------------------
    if mode == "fast":
        ok_fast = [it for it in ok_items if int(it["cmd"]) >= 0]
        if not ok_fast:
            return None

        ok_fast.sort(key=lambda it: int(it["abs_peak"]))

        best_candidate = None

        for i, first in enumerate(ok_fast):
            if should_stop is not None and should_stop():
                print("[realtime_listener] stop requested during fast pairing scan")
                break

            partner = None
            for second in ok_fast[i + 1:]:
                if should_stop is not None and should_stop():
                    print("[realtime_listener] stop requested during fast repeat scan")
                    break

                if int(second["abs_peak"]) <= int(first["abs_peak"]):
                    continue

                expect = _expected_repeat_offset_samples(cfg)
                tol = int(round(rt_cfg.fast_repeat_tol_s * cfg.sr))
                delta = int(second["abs_peak"]) - int(first["abs_peak"])
                if delta > expect + tol:
                    break

                if (
                    _is_expected_fast_repeat(
                        int(first["abs_peak"]),
                        int(second["abs_peak"]),
                        cfg,
                        rt_cfg,
                    )
                    and int(second["cmd"]) == int(first["cmd"])
                    and int(second["seq"]) == int(first["seq"])
                ):
                    partner = second
                    break

            vote_count = 2 if partner is not None else 1
            need = _required_accept_min(mode, int(first["cmd"]), rt_cfg)
            if vote_count < need:
                continue

            best_item = first
            best_score = float(first["score"])
            if partner is not None and float(partner["score"]) > best_score:
                best_item = partner
                best_score = float(partner["score"])

            if best_score < _accept_score_min_for_mode(mode, rt_cfg):
                continue

            cand = {
                "mode": mode,
                "cfg": cfg,
                "cmd": int(first["cmd"]),
                "seq": int(first["seq"]),
                "vote_count": int(vote_count),
                "vote_total": int(vote_count),
                "best_score": float(best_score),
                "frames": frame_results,
                "decoded_ok": [(int(it["cmd"]), int(it["seq"])) for it in ok_fast],
                "best_item": best_item,
            }

            if best_candidate is None:
                best_candidate = cand
            else:
                if (
                    int(cand["vote_count"]) > int(best_candidate["vote_count"])
                    or (
                        int(cand["vote_count"]) == int(best_candidate["vote_count"])
                        and float(cand["best_score"]) > float(best_candidate["best_score"])
                    )
                ):
                    best_candidate = cand

        return best_candidate

    # -------------------------
    # slow: keep old behavior
    # -------------------------
    summary = _summarize_ok_frames(mode, ok_items, rt_cfg)
    if summary is None:
        return None

    return {
        "mode": mode,
        "cfg": cfg,
        "cmd": int(summary["cmd"]),
        "seq": int(summary["seq"]),
        "vote_count": int(summary["vote_count"]),
        "vote_total": len(ok_items),
        "best_score": float(summary["best_score"]),
        "frames": frame_results,
        "decoded_ok": [(int(it["cmd"]), int(it["seq"])) for it in ok_items],
        "best_item": summary["best_item"],
    }


def _choose_best_candidate(candidates: list[dict | None]) -> dict | None:
    valid = [c for c in candidates if c is not None]
    if not valid:
        return None

    return max(
        valid,
        key=lambda c: (
            int(c["vote_count"]),
            float(c["best_score"]),
            len(c["decoded_ok"]),
        ),
    )


def listen_forever(
    fast_cfg: AcousticConfig,
    slow_cfg: AcousticConfig,
    rt_cfg: RealtimeListenerConfig,
    device: int | None = None,
    on_trigger: Optional[Callable[[int, int, dict[str, Any]], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Realtime acoustic listener for both fast and slow protocols.

    Core difference from the old version:
    it is stateful and only processes NEW chirp peaks.
    """
    if fast_cfg.sr != slow_cfg.sr:
        raise ValueError("fast_cfg.sr and slow_cfg.sr must match")

    sr = fast_cfg.sr
    input_sr = sr if rt_cfg.input_sr is None else int(rt_cfg.input_sr)

    # decode/protocol domain
    hop = max(1, int(round(rt_cfg.hop_s * sr)))
    ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))
    ring = np.zeros(ring_len, dtype=np.float32)

    # device/capture domain
    hop_in = max(1, int(round(rt_cfg.hop_s * input_sr)))
    raw_ring_len = max(hop_in, int(round(rt_cfg.ring_s * input_sr)))
    raw_ring = np.zeros(raw_ring_len, dtype=np.float32)

    fast_tpl = make_chirp_template(
        sr=fast_cfg.sr,
        chirp_dur=fast_cfg.chirp_dur,
        f0=fast_cfg.chirp_f0,
        f1=fast_cfg.chirp_f1,
        fade_len=fast_cfg.fade_len,
    )
    slow_tpl = make_chirp_template(
        sr=slow_cfg.sr,
        chirp_dur=slow_cfg.chirp_dur,
        f0=slow_cfg.chirp_f0,
        f1=slow_cfg.chirp_f1,
        fade_len=slow_cfg.fade_len,
    )

    fast_state = ModeScanState()
    slow_state = ModeScanState()

    capture_dir = Path(rt_cfg.capture_dir)
    if rt_cfg.save_capture:
        capture_dir.mkdir(parents=True, exist_ok=True)

    print("=== Realtime acoustic listener (stateful) ===")
    print(
        f"sr={sr}, input_sr={input_sr}, hop={rt_cfg.hop_s}s, ring={rt_cfg.ring_s}s, "
        f"fast_thresh={rt_cfg.fast_chirp_thresh}, slow_thresh={rt_cfg.slow_chirp_thresh}, "
        f"fast_accept_min={rt_cfg.fast_accept_min}, "
        f"slow_accept_min={rt_cfg.slow_accept_min}, "
        f"stop_accept_min={rt_cfg.stop_accept_min}, "
        f"fast_holdoff={rt_cfg.fast_post_accept_s}s, "
        f"slow_holdoff={rt_cfg.slow_post_accept_s}s, "
        f"stop_holdoff={rt_cfg.stop_post_accept_s}s"
    )
    print(
        "fast_chirp="
        f"{fast_cfg.chirp_f0:.0f}->{fast_cfg.chirp_f1:.0f} dur={fast_cfg.chirp_dur:.3f}s | "
        "slow_chirp="
        f"{slow_cfg.chirp_f0:.0f}->{slow_cfg.chirp_f1:.0f} dur={slow_cfg.chirp_dur:.3f}s"
    )
    if device is not None:
        print(f"input_device={device}")
    print("Press Ctrl+C to stop.\n")

    last_debug_t = 0.0
    suppress_until = 0.0
    sample_clock = 0  # absolute sample count in decode/protocol domain

    warmup_until_samples = int(round(rt_cfg.startup_warmup_s * sr))

    try:
        with open_input_stream(
            sr=input_sr,
            blocksize=hop_in,
            device=device,
            dtype="float32",
            channels=1,
        ) as stream:
            while True:
                if should_stop is not None and should_stop():
                    print("[realtime_listener] stop requested, exiting main loop")
                    break

                raw_block, _overflowed = stream.read(hop_in)
                raw_block = np.asarray(raw_block, dtype=np.float32).reshape(-1)

                mic_level = float(np.max(np.abs(raw_block))) if len(raw_block) else 0.0

                # maintain raw input ring
                _update_ring(raw_ring, raw_block)

                # resample the whole raw ring into the protocol domain
                ring_rs = _resample_block(raw_ring, src_sr=input_sr, dst_sr=sr)

                # keep fixed-length decode ring and preserve the newest samples
                if len(ring_rs) >= ring_len:
                    ring[:] = ring_rs[-ring_len:]
                else:
                    ring[:] = 0.0
                    ring[-len(ring_rs):] = ring_rs

                # advance decode-domain clock by one protocol hop
                sample_clock += hop
                ring_start_abs = int(sample_clock - len(ring))

                now_wall = float(
                    np.round(
                        np.float64(
                            np.datetime64("now").astype("datetime64[ms]").astype(int)
                        ) / 1000.0,
                        3,
                    )
                )
                now_mono = time.monotonic()

                # startup warmup phase
                if sample_clock < warmup_until_samples:
                    if should_stop is not None and should_stop():
                        print("[realtime_listener] stop requested during warmup")
                        return

                    if rt_cfg.clear_ring_after_accept:
                        ring[:] = 0.0
                        raw_ring[:] = 0.0
                    fast_state.last_peak_abs = sample_clock
                    slow_state.last_peak_abs = sample_clock
                    last_debug_t = now_wall
                    continue

                # hard suppress after accepted trigger:
                # ignore the tail of the same wav
                if now_mono < suppress_until:
                    if should_stop is not None and should_stop():
                        print("[realtime_listener] stop requested during suppress window")
                        return

                    if rt_cfg.clear_ring_after_accept:
                        ring[:] = 0.0
                        raw_ring[:] = 0.0
                    fast_state.last_peak_abs = sample_clock
                    slow_state.last_peak_abs = sample_clock

                    if now_wall - last_debug_t >= rt_cfg.debug_every_s:
                        remain = max(0.0, suppress_until - now_mono)
                        clip_tag = " CLIP!" if mic_level >= rt_cfg.clip_warn_level else ""
                        print(
                            f"[dbg] mic={mic_level:.4f}{clip_tag} suppressed={remain:.2f}s "
                            f"fast_ready=False fast_score=0.0000 "
                            f"slow_ready=False slow_score=0.0000 chosen=none"
                        )
                        last_debug_t = now_wall
                    continue

                fast_candidate = _collect_mode_candidate(
                    wave=ring,
                    mode="fast",
                    cfg=fast_cfg,
                    chirp_tpl=fast_tpl,
                    rt_cfg=rt_cfg,
                    ring_start_abs=ring_start_abs,
                    state=fast_state,
                    should_stop=should_stop,
                )
                if should_stop is not None and should_stop():
                    print("[realtime_listener] stop requested after fast scan")
                    break

                slow_candidate = _collect_mode_candidate(
                    wave=ring,
                    mode="slow",
                    cfg=slow_cfg,
                    chirp_tpl=slow_tpl,
                    rt_cfg=rt_cfg,
                    ring_start_abs=ring_start_abs,
                    state=slow_state,
                    should_stop=should_stop,
                )
                if should_stop is not None and should_stop():
                    print("[realtime_listener] stop requested after slow scan")
                    break

                chosen = _choose_best_candidate([fast_candidate, slow_candidate])

                if now_wall - last_debug_t >= rt_cfg.debug_every_s:
                    fast_ready = fast_candidate is not None
                    slow_ready = slow_candidate is not None
                    fast_score = 0.0 if fast_candidate is None else float(fast_candidate["best_score"])
                    slow_score = 0.0 if slow_candidate is None else float(slow_candidate["best_score"])
                    chosen_mode = "none" if chosen is None else str(chosen["mode"])
                    clip_tag = " CLIP!" if mic_level >= rt_cfg.clip_warn_level else ""
                    print(
                        f"[dbg] mic={mic_level:.4f}{clip_tag} "
                        f"fast_ready={fast_ready} fast_score={fast_score:.4f} "
                        f"slow_ready={slow_ready} slow_score={slow_score:.4f} "
                        f"chosen={chosen_mode}"
                    )

                    if rt_cfg.save_debug_ring:
                        write_wav(rt_cfg.debug_ring_path, ring, sr)

                    last_debug_t = now_wall

                if chosen is None:
                    continue

                info = {
                    "mode": chosen["mode"],
                    "cmd": int(chosen["cmd"]),
                    "seq": int(chosen["seq"]),
                    "vote_count": int(chosen["vote_count"]),
                    "vote_total": int(chosen["vote_total"]),
                    "best_score": float(chosen["best_score"]),
                    "cmd_name": cmd_name(int(chosen["cmd"])),
                    "is_stop_command": int(chosen["cmd"]) == STOP_CMD,
                    "input_level": float(mic_level),
                    "frames": chosen["frames"],
                    "decoded_ok": chosen["decoded_ok"],
                    "fast_candidate": fast_candidate,
                    "slow_candidate": slow_candidate,
                }

                print(
                    f"✅ trigger accepted: mode={chosen['mode']} "
                    f"cmd=0x{chosen['cmd']:02X} ({cmd_name(chosen['cmd'])}) "
                    f"seq={chosen['seq']} "
                    f"(votes {chosen['vote_count']}/{max(1, chosen['vote_total'])}, "
                    f"score={chosen['best_score']:.4f})"
                )

                if rt_cfg.save_capture:
                    stamp = np.datetime64("now", "s").astype(str).replace(":", "-")
                    out_path = capture_dir / f"{rt_cfg.capture_prefix}_{stamp}.wav"
                    write_wav(str(out_path), ring, sr)
                    print(f"   saved capture: {out_path}")

                if on_trigger is not None:
                    on_trigger(chosen["cmd"], chosen["seq"], info)

                suppress_until = now_mono + _post_accept_holdoff_s(
                    chosen["mode"],
                    chosen["cmd"],
                    rt_cfg,
                )

                # after accept: forget everything up to "now"
                fast_state.last_peak_abs = sample_clock
                slow_state.last_peak_abs = sample_clock

                if rt_cfg.clear_ring_after_accept:
                    ring[:] = 0.0
                    raw_ring[:] = 0.0

    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> None:
    rt_cfg = RealtimeListenerConfig(
        fast_accept_min=1,
        slow_accept_min=1,
        stop_accept_min=2,
        clear_ring_after_accept=True,
        fast_post_accept_s=1.25,
        slow_post_accept_s=2.0,
        stop_post_accept_s=3.0,
        fast_chirp_thresh=0.05,
        slow_chirp_thresh=0.10,
        fast_repeat_tol_s=0.05,
        clip_warn_level=0.90,
        fast_accept_score_min=0.15,
        startup_warmup_s=1.5,
        input_sr=48000,
        verbose_debug=False,
    )
    listen_forever(
        fast_cfg=FAST_CONFIG,
        slow_cfg=SLOW_CONFIG,
        rt_cfg=rt_cfg,
        device=0,
        on_trigger=None,
        should_stop=None,
    )


if __name__ == "__main__":
    main()