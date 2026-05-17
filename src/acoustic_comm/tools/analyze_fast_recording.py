from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import argparse
import math
import wave

import numpy as np

from acoustic_comm.protocol.constants import FAST_CONFIG
from acoustic_comm.rx.offline_decode import decode_from_wave


FAST_CMDS = {
    "start_splice": 0x8A,
    "enter_merlin": 0x27,
    "climb_merlin": 0xE1,
    "leave_merlin": 0x72,
}


def cmd_to_bits(cmd: int, nbits: int = 8) -> list[int]:
    return [(cmd >> (nbits - 1 - i)) & 1 for i in range(nbits)]


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 1:
        x = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        x = (x - 128.0) / 128.0
    elif sampwidth == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    if n_channels > 1:
        x = x.reshape(-1, n_channels).mean(axis=1)

    return x.astype(np.float32), sr


def linear_resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    t_in = np.arange(len(x), dtype=np.float64) / float(sr_in)
    dur = len(x) / float(sr_in)
    n_out = int(round(dur * sr_out))
    t_out = np.arange(n_out, dtype=np.float64) / float(sr_out)
    y = np.interp(t_out, t_in, x).astype(np.float32)
    return y


def dft_bin_energy(seg: np.ndarray, sr: int, freq: float) -> float:
    n = len(seg)
    if n == 0:
        return 0.0
    t = np.arange(n, dtype=np.float64) / float(sr)
    w = np.hanning(n).astype(np.float64)
    z = np.sum(seg.astype(np.float64) * w * np.exp(-2j * np.pi * freq * t))
    return float((z.real * z.real + z.imag * z.imag) / (np.sum(w) ** 2 + 1e-12))


def bit_energy_report(
    x: np.ndarray,
    sr: int,
    payload_start: int,
    bit_dur: float,
    cmd_bits: int,
    f0: float,
    f1: float,
) -> list[dict]:
    n_bit = int(round(bit_dur * sr))
    rows: list[dict] = []

    for i in range(cmd_bits):
        s = payload_start + i * n_bit
        e = s + n_bit
        if s < 0 or e > len(x):
            break

        seg = x[s:e]
        e0 = dft_bin_energy(seg, sr, f0)
        e1 = dft_bin_energy(seg, sr, f1)
        bit_hat = 1 if e1 > e0 else 0
        margin_db = 10.0 * math.log10((e1 + 1e-12) / (e0 + 1e-12))

        rows.append(
            {
                "bit_idx": i,
                "e0": e0,
                "e1": e1,
                "bit_hat": bit_hat,
                "margin_db": margin_db,
            }
        )

    return rows


def pick_best_frame(res: dict) -> dict | None:
    frames = res.get("frames", [])
    if not frames:
        return None
    return max(frames, key=lambda fr: float(fr.get("score", -1e18)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True, help="录音 wav 文件路径")
    parser.add_argument("--expect", default=None, help="期望命令名，如 start_splice")
    parser.add_argument("--f0", type=float, default=1500.0)
    parser.add_argument("--f1", type=float, default=2500.0)
    parser.add_argument("--chirp-f0", type=float, default=1200.0)
    parser.add_argument("--chirp-f1", type=float, default=3200.0)
    args = parser.parse_args()

    cfg = replace(
        FAST_CONFIG,
        f0=args.f0,
        f1=args.f1,
        chirp_f0=args.chirp_f0,
        chirp_f1=args.chirp_f1,
    )

    wav_path = Path(args.wav)
    x, sr_in = read_wav_mono(wav_path)
    x = linear_resample(x, sr_in, cfg.sr)

    print("=== decode_from_wave ===")
    res = decode_from_wave(x, cfg=cfg)
    print(res)

    best = pick_best_frame(res)
    if best is None:
        print("\nNo frame found in result['frames'].")
        return

    payload_start = int(best["payload_start"])
    score = float(best.get("score", 0.0))
    decoded_cmd = best.get("cmd", None)
    bits = best.get("bits", None)

    print("\n=== best frame ===")
    print(f"score         : {score:.6f}")
    print(f"payload_start : {payload_start}")
    print(f"decoded_cmd   : {decoded_cmd} ({hex(decoded_cmd) if decoded_cmd is not None else None})")
    print(f"decoded_bits  : {bits}")

    expect_bits = None
    if args.expect is not None:
        if args.expect not in FAST_CMDS:
            raise ValueError(f"Unknown expect name: {args.expect}")
        expect_cmd = FAST_CMDS[args.expect]
        expect_bits = cmd_to_bits(expect_cmd, cfg.cmd_bits)
        print(f"expect_cmd    : {expect_cmd} ({hex(expect_cmd)})")
        print(f"expect_bits   : {expect_bits}")

    rows = bit_energy_report(
        x=x,
        sr=cfg.sr,
        payload_start=payload_start,
        bit_dur=cfg.bit_dur,
        cmd_bits=cfg.cmd_bits,
        f0=cfg.f0,
        f1=cfg.f1,
    )

    print("\n=== per-bit energy ===")
    print("idx |   E(f0)    |   E(f1)    | hat | margin_db | expect")
    print("-" * 62)
    for row in rows:
        idx = row["bit_idx"]
        exp = "-" if expect_bits is None or idx >= len(expect_bits) else str(expect_bits[idx])
        print(
            f"{idx:3d} | "
            f"{row['e0']:10.6e} | "
            f"{row['e1']:10.6e} | "
            f"{row['bit_hat']:3d} | "
            f"{row['margin_db']:9.3f} | "
            f"{exp}"
        )

    if expect_bits is not None and rows:
        hats = [r["bit_hat"] for r in rows]
        mismatches = [i for i, (a, b) in enumerate(zip(hats, expect_bits)) if a != b]
        print("\n=== compare to expected ===")
        print(f"mismatch_positions: {mismatches}")


if __name__ == "__main__":
    main()