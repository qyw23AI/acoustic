# src/acoustic_comm/io/wav.py
from __future__ import annotations
import numpy as np
import soundfile as sf


def read_wav(path: str) -> tuple[np.ndarray, int]:
    """
    Read wav as float32 mono.
    Returns: (x, sr)
    """
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    if isinstance(x, np.ndarray) and x.ndim > 1:
        x = x[:, 0]  # take first channel
    return np.asarray(x, dtype=np.float32), int(sr)


def write_wav(path: str, x: np.ndarray, sr: int) -> None:
    """
    Write float waveform to wav.
    """
    x = np.asarray(x, dtype=np.float32)
    sf.write(path, x, sr)