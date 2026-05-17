from __future__ import annotations

import numpy as np

from ..dsp.chirp_sync import make_chirp_template, find_topk_chirp_peaks
from ..dsp.fsk import decode_bits_from
from ..protocol.constants import AcousticConfig
from ..protocol.frame import bits_to_bytes, check_frame
from .postprocess import majority_vote


def decode_frame_at_peak(
    x: np.ndarray,
    peak: int,
    score: float,
    cfg: AcousticConfig,
) -> dict:
    """
    Decode one frame given a chirp start index.

    Returns a debug-friendly dict.

    Notes
    -----
    - payload starts immediately after chirp
    - when seq is disabled in cfg, returned seq will be 0
    """
    payload_start = int(peak) + cfg.chirp_len
    nbits = cfg.frame_bits

    bits = decode_bits_from(
        x=np.asarray(x, dtype=np.float32),
        start_idx=payload_start,
        nbits=nbits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
    )

    if bits is None or len(bits) != nbits:
        return {
            "ok": False,
            "reason": "not_enough_bits",
            "peak": int(peak),
            "score": float(score),
            "payload_start": payload_start,
            "got_bits": 0 if bits is None else len(bits),
            "need_bits": nbits,
        }

    frame_bytes = bits_to_bytes(bits, msb_first=cfg.msb_first)
    ok, cmd, seq = check_frame(frame_bytes, cfg)

    return {
        "ok": bool(ok),
        "reason": None if ok else "frame_check_failed",
        "cmd": int(cmd),
        "seq": int(seq),
        "bits": bits,
        "frame_bytes": frame_bytes,
        "peak": int(peak),
        "score": float(score),
        "payload_start": payload_start,
    }


def decode_from_wave(
    x: np.ndarray,
    cfg: AcousticConfig,
    score_thresh: float = 1e-6,
    vote_min: int | None = None,
    min_gap_s: float = 0.25,
) -> dict:
    """
    Offline decode entry.

    Strategy
    --------
    1) Build normalized chirp template
    2) Find top-k chirp peaks (k ~= repeat_n)
    3) Decode one frame after each peak
    4) Check each frame (CRC if enabled by cfg)
    5) Majority-vote valid decoded results

    Returns
    -------
    dict
        A debug-friendly result dict.

    Notes
    -----
    - In no-seq modes, vote is effectively over (cmd, 0)
    - In legacy mode, vote is over (cmd, seq)
    """
    wave = np.asarray(x, dtype=np.float32)

    if vote_min is None:
        vote_min = 1 if cfg.repeat_n <= 1 else 2

    tpl = make_chirp_template(
        sr=cfg.sr,
        chirp_dur=cfg.chirp_dur,
        f0=cfg.chirp_f0,
        f1=cfg.chirp_f1,
        fade_len=cfg.fade_len,
    )

    peaks = find_topk_chirp_peaks(
        x=wave,
        chirp_tpl=tpl,
        sr=cfg.sr,
        k=cfg.repeat_n,
        min_gap_s=min_gap_s,
        score_threshold=score_thresh,
        use_abs=True,
    )

    if not peaks:
        return {
            "ok": False,
            "reason": "no_chirp_peak",
            "peaks": [],
            "frames": [],
        }

    frame_results: list[dict] = []
    decoded_ok: list[tuple[int, int]] = []

    for peak, score in peaks:
        item = decode_frame_at_peak(wave, peak=peak, score=score, cfg=cfg)
        frame_results.append(item)
        if item["ok"]:
            decoded_ok.append((item["cmd"], item["seq"]))

    vote = majority_vote(decoded_ok, min_count=vote_min)
    if vote is None:
        return {
            "ok": False,
            "reason": "vote_failed",
            "peaks": [(int(p), float(s)) for p, s in peaks],
            "frames": frame_results,
            "decoded_ok": decoded_ok,
            "vote_min": int(vote_min),
        }

    return {
        "ok": True,
        "reason": None,
        "cmd": int(vote.cmd),
        "seq": int(vote.seq),
        "vote_count": int(vote.count),
        "vote_total": int(vote.total),
        "peaks": [(int(p), float(s)) for p, s in peaks],
        "frames": frame_results,
        "decoded_ok": decoded_ok,
        "vote_min": int(vote_min),
    }