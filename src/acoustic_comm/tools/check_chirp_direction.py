from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np


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


def dominant_freq(seg: np.ndarray, sr: int, fmin: float, fmax: float) -> float:
    seg = np.asarray(seg, dtype=np.float64)
    if len(seg) == 0:
        return float("nan")

    w = np.hanning(len(seg))
    y = seg * w

    spec = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(len(y), d=1.0 / sr)

    mask = (freqs >= fmin) & (freqs <= fmax)
    if not np.any(mask):
        return float("nan")

    idx = np.argmax(np.abs(spec[mask]))
    return float(freqs[mask][idx])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True, help="要检查的 wav")
    parser.add_argument("--head-s", type=float, default=0.02, help="chirp 前静音时长")
    parser.add_argument("--chirp-s", type=float, default=0.08, help="chirp 时长")
    parser.add_argument("--band-low", type=float, default=800.0)
    parser.add_argument("--band-high", type=float, default=3800.0)
    args = parser.parse_args()

    x, sr = read_wav_mono(Path(args.wav))

    head_n = int(round(args.head_s * sr))
    chirp_n = int(round(args.chirp_s * sr))

    s = head_n
    e = s + chirp_n
    if e > len(x):
        raise ValueError("wav 太短，拿不到 chirp 段")

    chirp = x[s:e]

    # 取 chirp 前 20% 和后 20% 做主频估计
    part_n = max(64, int(round(0.2 * len(chirp))))
    first = chirp[:part_n]
    last = chirp[-part_n:]

    f_first = dominant_freq(first, sr, args.band_low, args.band_high)
    f_last = dominant_freq(last, sr, args.band_low, args.band_high)

    print(f"wav       : {args.wav}")
    print(f"sr        : {sr}")
    print(f"head_n    : {head_n}")
    print(f"chirp_n   : {chirp_n}")
    print(f"f_first   : {f_first:.1f} Hz")
    print(f"f_last    : {f_last:.1f} Hz")

    if np.isnan(f_first) or np.isnan(f_last):
        print("direction : unknown")
    elif f_last > f_first:
        print("direction : upchirp")
    elif f_last < f_first:
        print("direction : downchirp")
    else:
        print("direction : flat/unknown")


if __name__ == "__main__":
    main()