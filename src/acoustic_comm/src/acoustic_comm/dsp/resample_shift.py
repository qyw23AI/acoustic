from __future__ import annotations

import numpy as np


def normalize_peak(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    """
    Peak-normalize waveform to [-peak, peak] approximately.
    Returns float32 waveform.
    """
    y = np.asarray(x, dtype=np.float32).copy()
    if len(y) == 0:
        return y

    m = float(np.max(np.abs(y)))
    if m <= 1e-12:
        return y
    return (y / m * float(peak)).astype(np.float32)


def time_stretch_linear(
    x: np.ndarray,
    stretch: float,
    peak: float = 0.9,
    keep_length: bool = True,
) -> np.ndarray:
    """
    Simulate sampling-rate / clock mismatch by linear time stretching.

    Parameters
    ----------
    x : np.ndarray
        Input waveform.
    stretch : float
        stretch > 1.0 -> longer waveform (as if RX/TX clock is slower)
        stretch < 1.0 -> shorter waveform (as if RX/TX clock is faster)
    peak : float
        Peak normalization target after transform.
    keep_length : bool
        If True, crop/pad result back to original length so downstream
        decoders can keep fixed indexing assumptions.

    Returns
    -------
    np.ndarray
        Float32 waveform.
    """
    if not np.isfinite(stretch) or stretch <= 0.0:
        raise ValueError(f"stretch must be positive and finite, got {stretch}")

    y = np.asarray(x, dtype=np.float32)
    n = len(y)
    if n == 0:
        return np.zeros(0, dtype=np.float32)

    new_n = max(1, int(round(n * float(stretch))))

    xp = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
    xq = np.linspace(0.0, 1.0, new_n, endpoint=False, dtype=np.float32)
    z = np.interp(xq, xp, y).astype(np.float32)

    if keep_length:
        if len(z) > n:
            z = z[:n]
        elif len(z) < n:
            z = np.pad(z, (0, n - len(z))).astype(np.float32)

    return normalize_peak(z, peak=peak)


def freq_shift_multiply(
    x: np.ndarray,
    hz: float,
    sr: int,
    peak: float = 0.9,
) -> np.ndarray:
    """
    Simulate carrier/frequency offset by multiplying waveform with a cosine.

    Notes
    -----
    This is an engineering stress-test approximation, not a full physical
    acoustic-channel model. It is useful for robustness evaluation.

    Parameters
    ----------
    x : np.ndarray
        Input waveform.
    hz : float
        Frequency shift in Hz.
    sr : int
        Sample rate.
    peak : float
        Peak normalization target after transform.

    Returns
    -------
    np.ndarray
        Float32 waveform.
    """
    if sr <= 0:
        raise ValueError(f"sr must be positive, got {sr}")

    y = np.asarray(x, dtype=np.float32)
    n = len(y)
    if n == 0:
        return np.zeros(0, dtype=np.float32)

    t = np.arange(n, dtype=np.float32) / float(sr)
    c = np.cos(2.0 * np.pi * float(hz) * t).astype(np.float32)
    z = (y * c).astype(np.float32)

    return normalize_peak(z, peak=peak)