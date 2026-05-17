from __future__ import annotations

import argparse
from collections import Counter

import numpy as np

from ..dsp.chirp_sync import make_chirp_template, find_topk_chirp_peaks
from ..dsp.fsk import decode_bits_from
from ..protocol.constants import DEFAULT_CONFIG, AcousticConfig
from ..protocol.frame import bits_to_bytes, check_frame


def pink_noise(n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    scale = np.ones_like(freqs, dtype=np.float64)
    scale[1:] = 1.0 / np.sqrt(freqs[1:])

    xr = np.fft.rfft(rng.standard_normal(n))
    xr = xr * scale
    x = np.fft.irfft(xr, n=n).astype(np.float32)

    peak = float(np.max(np.abs(x)))
    if peak > 1e-12:
        x = x / peak
    return (0.6 * x).astype(np.float32)


def white_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    x = rng.standard_normal(n).astype(np.float32)
    peak = float(np.max(np.abs(x)))
    if peak > 1e-12:
        x = x / peak
    return (0.6 * x).astype(np.float32)


def _decode_frame_at_peak(x: np.ndarray, peak: int, cfg: AcousticConfig) -> tuple[bool, int, int]:
    payload_start = peak + cfg.chirp_len
    bits = decode_bits_from(
        x=x,
        start_idx=payload_start,
        nbits=cfg.frame_bits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
    )
    if bits is None or len(bits) != cfg.frame_bits:
        return False, 0, 0

    frame_bytes = bits_to_bytes(bits, msb_first=cfg.msb_first)
    return check_frame(frame_bytes, cfg)


def run_false_alarm_test(
    cfg: AcousticConfig,
    seconds: float,
    noise_kind: str,
    chirp_thresh: float,
    vote_min: int,
    scan_hop_s: float,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)
    n = int(round(seconds * cfg.sr))

    if noise_kind == "white":
        x = white_noise(n, rng)
    else:
        x = pink_noise(n, cfg.sr, rng)

    hop = max(1, int(round(scan_hop_s * cfg.sr)))
    tpl = make_chirp_template(cfg.sr, cfg.chirp_dur, cfg.chirp_f0, cfg.chirp_f1)

    crc_pass = 0
    triggers = 0
    trigger_times: list[float] = []

    cooldown_samples = int(round(0.5 * cfg.sr))
    cooldown = 0

    i = 0
    scan_len = cfg.chirp_len + cfg.repeat_n * (cfg.frame_bits * cfg.bit_len)
    while i + scan_len < len(x):
        if cooldown > 0:
            cooldown -= hop
            i += hop
            continue

        win = x[i : i + scan_len]
        peaks = find_topk_chirp_peaks(
            x=win,
            chirp_tpl=tpl,
            sr=cfg.sr,
            k=cfg.repeat_n,
            min_gap_s=cfg.gap_s + cfg.chirp_dur,
            score_threshold=chirp_thresh,
            use_abs=True,
        )

        decoded: list[tuple[int, int]] = []
        for peak, _score in peaks:
            ok, cmd, seq = _decode_frame_at_peak(win, peak, cfg)
            if ok:
                crc_pass += 1
                decoded.append((cmd, seq))

        if decoded:
            winner, cnt = Counter(decoded).most_common(1)[0]
            if cnt >= vote_min:
                triggers += 1
                trigger_times.append(i / cfg.sr)
                cooldown = cooldown_samples

        i += hop

    return {
        "seconds": float(seconds),
        "noise_kind": noise_kind,
        "chirp_thresh": float(chirp_thresh),
        "vote_min": int(vote_min),
        "scan_hop_s": float(scan_hop_s),
        "crc_pass": int(crc_pass),
        "triggers": int(triggers),
        "trigger_times": trigger_times,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="False-alarm test on pure noise.")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--noise", type=str, choices=["pink", "white"], default="pink")
    parser.add_argument("--chirp-thresh", type=float, default=0.20)
    parser.add_argument("--vote-min", type=int, default=2)
    parser.add_argument("--scan-hop-s", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    cfg = DEFAULT_CONFIG
    out = run_false_alarm_test(
        cfg=cfg,
        seconds=args.seconds,
        noise_kind=args.noise,
        chirp_thresh=args.chirp_thresh,
        vote_min=args.vote_min,
        scan_hop_s=args.scan_hop_s,
        seed=args.seed,
    )

    print("=== False-alarm test ===")
    print(
        f"seconds={out['seconds']} noise={out['noise_kind']} "
        f"hop={out['scan_hop_s']} chirp_thresh={out['chirp_thresh']} vote_min={out['vote_min']}"
    )
    print(f"CRC-pass frames: {out['crc_pass']}")
    print(f"Final triggers : {out['triggers']}")
    if out["trigger_times"]:
        print("Trigger times  :", ", ".join(f"{t:.2f}s" for t in out["trigger_times"]))
    else:
        print("Trigger times  : none")


if __name__ == "__main__":
    main()