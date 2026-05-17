from __future__ import annotations

import numpy as np
import sounddevice as sd


def query_devices():
    """
    Return raw sounddevice device list.
    """
    return sd.query_devices()


def list_input_devices() -> list[dict]:
    """
    Return a simplified list of available input-capable audio devices.
    """
    devices = sd.query_devices()
    out: list[dict] = []

    for idx, dev in enumerate(devices):
        max_in = int(dev.get("max_input_channels", 0))
        if max_in > 0:
            out.append(
                {
                    "index": idx,
                    "name": str(dev.get("name", "")),
                    "max_input_channels": max_in,
                    "default_samplerate": float(dev.get("default_samplerate", 0.0)),
                }
            )

    return out


def print_input_devices() -> None:
    """
    Print all available input-capable devices.
    """
    devices = list_input_devices()
    if not devices:
        print("No input audio devices found.")
        return

    print("Available input devices:")
    for dev in devices:
        print(
            f"[{dev['index']}] {dev['name']} | "
            f"in_ch={dev['max_input_channels']} | "
            f"default_sr={dev['default_samplerate']:.0f}"
        )


def record_mono(
    dur_s: float,
    sr: int,
    device: int | None = None,
    dtype: str = "float32",
) -> np.ndarray:
    """
    Record mono audio and return float32 waveform of shape (n,).
    """
    if dur_s <= 0:
        return np.zeros(0, dtype=np.float32)
    if sr <= 0:
        raise ValueError(f"sr must be positive, got {sr}")

    n = int(round(dur_s * sr))
    audio = sd.rec(
        n,
        samplerate=sr,
        channels=1,
        dtype=dtype,
        device=device,
    )
    sd.wait()

    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    return x


def open_input_stream(
    sr: int,
    blocksize: int,
    device: int | None = None,
    dtype: str = "float32",
    channels: int = 1,
) -> sd.InputStream:
    """
    Create an input stream for realtime listening.
    Caller is responsible for using it as a context manager.
    """
    if sr <= 0:
        raise ValueError(f"sr must be positive, got {sr}")
    if blocksize <= 0:
        raise ValueError(f"blocksize must be positive, got {blocksize}")
    if channels <= 0:
        raise ValueError(f"channels must be positive, got {channels}")

    return sd.InputStream(
        samplerate=sr,
        blocksize=blocksize,
        channels=channels,
        dtype=dtype,
        device=device,
    )