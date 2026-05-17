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
    return x.astype(np.float32)


def add_pink_noise(clean: np.ndarray, snr_db: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    noise = pink_noise(len(clean), sr, rng)

    clean_r = rms(clean)
    noise_r = rms(noise)
    target_noise_r = clean_r / (10 ** (snr_db / 20.0))
    noise = noise * (target_noise_r / (noise_r + 1e-12))

    mixed = clean + noise
    peak = float(np.max(np.abs(mixed)))
    if peak > 1e-12:
        mixed = mixed / peak * 0.9
    return mixed.astype(np.float32)


def make_simple_rir(
    sr: int,
    rt60_s: float = 0.35,
    taps: int = 14,
    max_delay_ms: float = 80.0,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    max_delay = max(1, int(round(max_delay_ms * sr / 1000.0)))
    delays = np.sort(rng.integers(0, max_delay, size=taps))

    t = delays / float(sr)
    tau = rt60_s / 6.0
    amps = np.exp(-t / (tau + 1e-12))
    amps = amps / (np.sum(np.abs(amps)) + 1e-12)

    h = np.zeros(max_delay + 1, dtype=np.float32)
    h[0] = 1.0
    for d, a in zip(delays, amps):
        h[d] += float(0.6 * a)

    return h.astype(np.float32)


def apply_reverb(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    y = np.convolve(np.asarray(x, dtype=np.float32), np.asarray(h, dtype=np.float32), mode="full")[: len(x)]
    peak = float(np.max(np.abs(y)))
    if peak > 1e-12:
        y = y / peak * 0.9
    return y.astype(np.float32)


def run_snr_sweep_pink_reverb(
    clean: np.ndarray,
    cfg: AcousticConfig,
    target_cmd: int,
    target_seq: int,
    snr_list: list[float],
    trials: int,
    rng: np.random.Generator,
    rt60_s: float = 0.35,
    taps: int = 14,
    max_delay_ms: float = 80.0,
    score_thresh: float = 1e-6,
    vote_min: int | None = None,
) -> tuple[list[dict], np.ndarray]:
    h = make_simple_rir(
        sr=cfg.sr,
        rt60_s=rt60_s,
        taps=taps,
        max_delay_ms=max_delay_ms,
        seed=0,
    )
    reverbed_clean = apply_reverb(clean, h)

    results: list[dict] = []
    for snr_db in snr_list:
        ok = 0
        for _ in range(trials):
            mixed = add_pink_noise(reverbed_clean, snr_db, cfg.sr, rng)
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

    return results, reverbed_clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Pink-noise + reverb SNR sweep.")
    parser.add_argument("--cmd", type=lambda s: int(s, 0), default=13)
    parser.add_argument("--seq", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--tx", type=str, default=None)
    parser.add_argument("--out-dir", type=str, default="eval_pink_reverb_out")
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--rt60", type=float, default=0.35)
    parser.add_argument("--taps", type=int, default=14)
    parser.add_argument("--max-delay-ms", type=float, default=80.0)
    parser.add_argument(
        "--snr",
        type=float,
        nargs="*",
        default=[0, -5, -10, -15, -20, -25],
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

    results, reverbed_clean = run_snr_sweep_pink_reverb(
        clean=clean,
        cfg=cfg,
        target_cmd=args.cmd,
        target_seq=args.seq,
        snr_list=list(args.snr),
        trials=args.trials,
        rng=rng,
        rt60_s=args.rt60,
        taps=args.taps,
        max_delay_ms=args.max_delay_ms,
    )

    print("=== Pink-noise + reverb SNR sweep ===")
    print(f"target: cmd={args.cmd}, seq={args.seq}, trials={args.trials}")
    print("-" * 68)
    for row in results:
        print(
            f"SNR={row['snr_db']:>5.1f} dB | "
            f"success {row['ok']:>2}/{row['trials']} | "
            f"rate={row['success_rate']:.2f}"
        )
        if args.save_examples:
            ex = add_pink_noise(reverbed_clean, row["snr_db"], cfg.sr, rng)
            write_wav(str(out_dir / f"pink_reverb_snr_{row['snr_db']:+.1f}dB.wav"), ex, cfg.sr)
    print("-" * 68)


if __name__ == "__main__":
    main()