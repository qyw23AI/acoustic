from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ..io.wav import read_wav, write_wav
from ..protocol.constants import DEFAULT_CONFIG, AcousticConfig
from ..tx.build_waveform import build_tx_wave


def rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float32)
    return float(np.sqrt(np.mean(x * x) + 1e-12))


def mix_at_snr(noise: np.ndarray, sig: np.ndarray, snr_db: float) -> tuple[np.ndarray, float]:
    """
    Mix sig into noise so that, over the overlapped region,
    RMS(sig_scaled) / RMS(noise_region) ~= 10^(snr_db / 20).
    """
    n = np.asarray(noise, dtype=np.float32).copy()
    s = np.asarray(sig, dtype=np.float32)

    L = min(len(n), len(s))
    n_seg = n[:L]
    s_seg = s[:L]

    rn = rms(n_seg)
    rs = rms(s_seg)

    target_rs = rn * (10 ** (snr_db / 20.0))
    scale = target_rs / (rs + 1e-12)

    mixed = n.copy()
    mixed[:L] = n_seg + s_seg * scale

    peak = float(np.max(np.abs(mixed)))
    if peak > 1e-12:
        mixed = mixed / peak * 0.9

    return mixed.astype(np.float32), float(scale)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mix TX waveform into stadium/background noise.")
    parser.add_argument("--noise", type=str, required=True, help="background noise wav")
    parser.add_argument("--tx", type=str, default=None, help="optional tx wav; if omitted, build from cmd/seq")
    parser.add_argument("--cmd", type=lambda s: int(s, 0), default=13)
    parser.add_argument("--seq", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--out-dir", type=str, default="stadium_mix_out")
    parser.add_argument("--snr", type=float, nargs="*", default=[10, 5, 0, -5])
    args = parser.parse_args()

    cfg: AcousticConfig = DEFAULT_CONFIG

    noise, sr_n = read_wav(args.noise)
    if sr_n != cfg.sr:
        raise ValueError(f"noise sample rate mismatch: {sr_n} vs {cfg.sr}")

    if args.tx is None:
        tx = build_tx_wave(args.cmd, args.seq, cfg)
    else:
        tx, sr_t = read_wav(args.tx)
        if sr_t != cfg.sr:
            raise ValueError(f"tx sample rate mismatch: {sr_t} vs {cfg.sr}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Stadium mix ===")
    for snr_db in args.snr:
        mixed, scale = mix_at_snr(noise, tx, snr_db)
        out_path = out_dir / f"stadium_mix_snr{snr_db:+.1f}dB.wav"
        write_wav(str(out_path), mixed, cfg.sr)
        print(f"{out_path} | tx_scale={scale:.4f}")


if __name__ == "__main__":
    main()