from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ..io.wav import read_wav, write_wav
from ..protocol.constants import DEFAULT_CONFIG, AcousticConfig
from ..rx.offline_decode import decode_from_wave
from ..tx.build_waveform import build_tx_wave


def rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float32)
    return float(np.sqrt(np.mean(x * x) + 1e-12))


def add_white_noise(clean: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    noise = rng.standard_normal(len(clean)).astype(np.float32)

    clean_r = rms(clean)
    noise_r = rms(noise)
    target_noise_r = clean_r / (10 ** (snr_db / 20.0))
    noise = noise * (target_noise_r / (noise_r + 1e-12))

    mixed = clean + noise
    peak = float(np.max(np.abs(mixed)))
    if peak > 1e-12:
        mixed = mixed / peak * 0.9
    return mixed.astype(np.float32)


def run_snr_sweep_white(
    clean: np.ndarray,
    cfg: AcousticConfig,
    target_cmd: int,
    target_seq: int,
    snr_list: list[float],
    trials: int,
    rng: np.random.Generator,
    score_thresh: float = 1e-6,
    vote_min: int | None = None,
) -> list[dict]:
    results: list[dict] = []

    for snr_db in snr_list:
        ok = 0
        for _ in range(trials):
            mixed = add_white_noise(clean, snr_db, rng)
            out = decode_from_wave(
                mixed,
                cfg=cfg,
                score_thresh=score_thresh,
                vote_min=vote_min,
            )
            if out.get("ok") and out.get("cmd") == target_cmd and out.get("seq") == target_seq:
                ok += 1

        results.append(
            {
                "snr_db": float(snr_db),
                "ok": int(ok),
                "trials": int(trials),
                "success_rate": float(ok / trials),
            }
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="White-noise SNR sweep for acoustic link.")
    parser.add_argument("--cmd", type=lambda s: int(s, 0), default=13)
    parser.add_argument("--seq", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--tx", type=str, default=None, help="optional input tx wav; if omitted, build from config")
    parser.add_argument("--out-dir", type=str, default="eval_white_out")
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--snr",
        type=float,
        nargs="*",
        default=[0, -5, -10, -15, -20, -25],
        help="SNR list in dB",
    )
    parser.add_argument("--save-examples", action="store_true")
    args = parser.parse_args()

    cfg = DEFAULT_CONFIG
    rng = np.random.default_rng(args.seed)

    if args.tx is None:
        clean = build_tx_wave(args.cmd, args.seq, cfg)
    else:
        clean, sr = read_wav(args.tx)
        if sr != cfg.sr:
            raise ValueError(f"sample rate mismatch: {sr} vs {cfg.sr}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = run_snr_sweep_white(
        clean=clean,
        cfg=cfg,
        target_cmd=args.cmd,
        target_seq=args.seq,
        snr_list=list(args.snr),
        trials=args.trials,
        rng=rng,
    )

    print("=== White-noise SNR sweep ===")
    print(f"target: cmd={args.cmd}, seq={args.seq}, trials={args.trials}")
    print("-" * 64)
    for row in results:
        print(
            f"SNR={row['snr_db']:>5.1f} dB | "
            f"success {row['ok']:>2}/{row['trials']} | "
            f"rate={row['success_rate']:.2f}"
        )
        if args.save_examples:
            ex = add_white_noise(clean, row["snr_db"], rng)
            write_wav(str(out_dir / f"white_snr_{row['snr_db']:+.1f}dB.wav"), ex, cfg.sr)
    print("-" * 64)


if __name__ == "__main__":
    main()