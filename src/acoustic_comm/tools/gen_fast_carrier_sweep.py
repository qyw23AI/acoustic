from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import wave
import numpy as np

from acoustic_comm.protocol.constants import FAST_CONFIG
from acoustic_comm.tx.build_waveform import build_tx_wave
from acoustic_comm.rx.offline_decode import decode_from_wave


FAST_CMDS = {
    "start_splice": 0x8A,
    "enter_merlin": 0x27,
    "climb_merlin": 0xE1,
    "leave_merlin": 0x72,
}

# 先测这几组；你后面可以自己再加
CARRIER_PAIRS = [
    (1500, 2500),
    (1800, 2800),
    (2000, 3000),
]

# 先把 fast chirp 显式写死，避免被当前仓库里别的配置带偏
FAST_CHIRP_F0 = 1200
FAST_CHIRP_F1 = 3200

OUT_DIR = Path("tmp/fast_carrier_sweep")


def save_wav_pcm16(path: Path, x: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 1:
        raise ValueError("Only mono wave is supported.")

    peak = float(np.max(np.abs(x))) if len(x) else 1.0
    if peak < 1e-12:
        peak = 1.0

    # 留一点头部，避免刚好顶满
    y = np.clip(x / peak * 0.95, -1.0, 1.0)
    y_i16 = (y * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(y_i16.tobytes())


def main() -> None:
    print("=== Generate fast carrier sweep wavs ===")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for f0, f1 in CARRIER_PAIRS:
        cfg = replace(
            FAST_CONFIG,
            f0=f0,
            f1=f1,
            chirp_f0=FAST_CHIRP_F0,
            chirp_f1=FAST_CHIRP_F1,
        )

        print(f"\n--- carrier pair: f0={f0}, f1={f1} ---")
        for name, cmd in FAST_CMDS.items():
            x = build_tx_wave(cmd, cfg=cfg)

            # 纯软件 sanity check，确保当前这组参数本身能离线解
            res = decode_from_wave(x, cfg=cfg)
            ok = bool(res.get("ok", False))
            vote_count = res.get("vote_count", None)
            vote_total = res.get("vote_total", None)
            decoded_cmd = res.get("cmd", None)

            out_name = f"fast_{name}_f0_{f0}_f1_{f1}.wav"
            out_path = OUT_DIR / out_name
            save_wav_pcm16(out_path, x, cfg.sr)

            print(
                f"{name:14s} cmd=0x{cmd:02X} "
                f"offline_ok={ok} decoded={decoded_cmd} "
                f"vote={vote_count}/{vote_total} -> {out_path}"
            )

    print("\nDone.")
    print(f"Wavs written to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()