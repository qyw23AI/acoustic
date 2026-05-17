from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd


def save_wav_pcm16(path: Path, x: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    x = np.clip(x, -1.0, 1.0)
    y = (x * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(y.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="输出 wav 路径")
    parser.add_argument("--dur", type=float, default=3.0, help="录音时长，秒")
    parser.add_argument("--sr", type=int, default=16000, help="采样率")
    parser.add_argument("--device", type=int, default=None, help="输入设备号，可选")
    args = parser.parse_args()

    n = int(round(args.dur * args.sr))

    print("=== recording ===")
    print(f"out    = {args.out}")
    print(f"dur    = {args.dur}s")
    print(f"sr     = {args.sr}")
    print(f"device = {args.device}")
    print("Start in 1 second...")
    sd.sleep(1000)

    rec = sd.rec(
        frames=n,
        samplerate=args.sr,
        channels=1,
        dtype="float32",
        device=args.device,
    )
    sd.wait()

    x = rec[:, 0]
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0

    save_wav_pcm16(Path(args.out), x, args.sr)

    print("Done.")
    print(f"peak={peak:.4f}, rms={rms:.4f}")


if __name__ == "__main__":
    main()