from __future__ import annotations

import argparse

import numpy as np

from ..eval.snr_sweep_white import add_white_noise
from ..io.wav import read_wav
from ..protocol.constants import DEFAULT_CONFIG, AcousticConfig
from ..rx.offline_decode import decode_from_wave
from ..tx.build_waveform import build_tx_wave
from ..dsp.resample_shift import time_stretch_linear, freq_shift_multiply


def run_drift_clock_grid(
    clean: np.ndarray,
    cfg: AcousticConfig,
    target_cmd: int,
    target_seq: int,
    stretch_list: list[float],
    freq_shift_list: list[float],
    snr_db: float,
    trials: int,
    rng: np.random.Generator,
) -> list[list[float]]:
    grid: list[list[float]] = []

    for stretch in stretch_list:
        row: list[float] = []
        for df in freq_shift_list:
            ok = 0
            for _ in range(trials):
                x = time_stretch_linear(clean, stretch=stretch, peak=0.9, keep_length=True)
                x = add_white_noise(x, snr_db, rng)
                x = freq_shift_multiply(x, hz=df, sr=cfg.sr, peak=0.9)

                out = decode_from_wave(x, cfg=cfg)
                if out.get("ok") and out.get("cmd") == target_cmd and out.get("seq") == target_seq:
                    ok += 1

            row.append(ok / trials)
        grid.append(row)

    return grid


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate freq drift and sampling-rate mismatch.")
    parser.add_argument("--cmd", type=lambda s: int(s, 0), default=13)
    parser.add_argument("--seq", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--tx", type=str, default=None)
    parser.add_argument("--snr-db", type=float, default=0.0)
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--stretch", type=float, nargs="*", default=[0.998, 0.999, 1.000, 1.001, 1.002])
    parser.add_argument("--df", type=float, nargs="*", default=[-120, -80, -40, 0, 40, 80, 120])
    args = parser.parse_args()

    cfg = DEFAULT_CONFIG
    rng = np.random.default_rng(args.seed)

    if args.tx is None:
        clean = build_tx_wave(args.cmd, args.seq, cfg)
    else:
        clean, sr = read_wav(args.tx)
        if sr != cfg.sr:
            raise ValueError(f"sample rate mismatch: {sr} vs {cfg.sr}")

    grid = run_drift_clock_grid(
        clean=clean,
        cfg=cfg,
        target_cmd=args.cmd,
        target_seq=args.seq,
        stretch_list=list(args.stretch),
        freq_shift_list=list(args.df),
        snr_db=args.snr_db,
        trials=args.trials,
        rng=rng,
    )

    print("=== Drift / clock grid ===")
    print(f"target: cmd={args.cmd}, seq={args.seq}, trials={args.trials}, snr_db={args.snr_db}")
    print(f"freq_shift_list = {list(args.df)}")
    print("-" * 80)
    for stretch, row in zip(args.stretch, grid):
        row_str = " ".join(f"{v:4.2f}" for v in row)
        print(f"stretch={stretch:.4f} | {row_str}")
    print("-" * 80)


if __name__ == "__main__":
    main()