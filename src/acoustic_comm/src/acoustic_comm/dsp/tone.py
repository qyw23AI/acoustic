from __future__ import annotations

import numpy as np


def apply_fade(x: np.ndarray, fade_len: int) -> np.ndarray:
    """
    Apply symmetric fade-in / fade-out and return float32 waveform.
    If fade_len <= 0 or waveform is too short, return a float32 copy.
    """
    y = np.asarray(x, dtype=np.float32).copy()

    if fade_len <= 0 or len(y) < 2:
        return y

    fade_len = min(fade_len, len(y) // 2)
    if fade_len <= 0:
        return y

    ramp = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
    y[:fade_len] *= ramp
    y[-fade_len:] *= ramp[::-1]
    return y


def tone(
    freq_hz: float,
    dur_s: float,
    sr: int,
    amp: float = 0.35,
    fade_len: int = 0,
) -> np.ndarray:
    """
    Generate sine tone waveform (float32).
    """
    n = int(round(dur_s * sr))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)

    t = np.arange(n, dtype=np.float32) / float(sr)
    x = amp * np.sin(2.0 * np.pi * float(freq_hz) * t)
    return apply_fade(x, fade_len)


def silence(dur_s: float, sr: int) -> np.ndarray:
    """
    Generate silence waveform (float32 zeros).
    """
    n = int(round(dur_s * sr))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    return np.zeros(n, dtype=np.float32)