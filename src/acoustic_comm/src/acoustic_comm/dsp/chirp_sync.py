from __future__ import annotations

import numpy as np
from scipy.signal import chirp

from .tone import apply_fade


def make_chirp(
    sr: int,
    chirp_dur: float,
    f0: float,
    f1: float,
    amp: float,
    fade_len: int = 0,
) -> np.ndarray:
    """
    Generate linear chirp waveform (float32), with optional symmetric fade.

    Parameters
    ----------
    sr : int
        Sample rate.
    chirp_dur : float
        Chirp duration in seconds.
    f0 : float
        Start frequency.
    f1 : float
        End frequency.
    amp : float
        Output amplitude scale.
    fade_len : int
        Optional fade length in samples.

    Returns
    -------
    np.ndarray
        Chirp waveform, float32.
    """
    n = int(round(chirp_dur * sr))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)

    t = np.arange(n, dtype=np.float32) / float(sr)
    x = chirp(
        t,
        f0=float(f0),
        t1=float(chirp_dur),
        f1=float(f1),
        method="linear",
    ).astype(np.float32)

    x = (float(amp) * x).astype(np.float32)
    return apply_fade(x, fade_len)


def make_chirp_template(
    sr: int,
    chirp_dur: float,
    f0: float,
    f1: float,
    fade_len: int = 0,
) -> np.ndarray:
    """
    Build normalized chirp template for correlation matching.

    Parameters
    ----------
    sr : int
        Sample rate.
    chirp_dur : float
        Chirp duration in seconds.
    f0 : float
        Start frequency.
    f1 : float
        End frequency.
    fade_len : int
        Optional fade length in samples. Should match TX chirp settings.

    Returns
    -------
    np.ndarray
        L2-normalized chirp template, float32.
    """
    tpl = make_chirp(
        sr=sr,
        chirp_dur=chirp_dur,
        f0=f0,
        f1=f1,
        amp=1.0,
        fade_len=fade_len,
    )
    norm = float(np.linalg.norm(tpl))
    if norm <= 1e-12:
        return tpl
    return (tpl / norm).astype(np.float32)


def chirp_correlation(x: np.ndarray, chirp_tpl: np.ndarray, use_abs: bool = True) -> np.ndarray:
    """
    Compute valid-mode correlation between signal and chirp template.

    Parameters
    ----------
    x : np.ndarray
        Input signal.
    chirp_tpl : np.ndarray
        Chirp template, usually normalized.
    use_abs : bool
        Whether to return abs(correlation), recommended for robust peak picking.

    Returns
    -------
    np.ndarray
        Correlation sequence, float32.
    """
    x = np.asarray(x, dtype=np.float32)
    tpl = np.asarray(chirp_tpl, dtype=np.float32)

    if len(x) < len(tpl) or len(tpl) == 0:
        return np.zeros(0, dtype=np.float32)

    corr = np.correlate(x, tpl, mode="valid").astype(np.float32)
    if use_abs:
        corr = np.abs(corr).astype(np.float32)
    return corr


def find_chirp_peak(x: np.ndarray, chirp_tpl: np.ndarray, use_abs: bool = True) -> tuple[int, float]:
    """
    Find the best chirp match in x.

    Returns
    -------
    (peak_idx, peak_score)
        peak_idx : int
            Approximate chirp start index in x.
        peak_score : float
            Correlation peak score.
    """
    corr = chirp_correlation(x, chirp_tpl, use_abs=use_abs)
    if len(corr) == 0:
        return 0, float("-inf")

    peak_idx = int(np.argmax(corr))
    peak_score = float(corr[peak_idx])
    return peak_idx, peak_score


def find_topk_chirp_peaks(
    x: np.ndarray,
    chirp_tpl: np.ndarray,
    sr: int,
    k: int = 3,
    min_gap_s: float = 0.25,
    score_threshold: float = 1e-6,
    use_abs: bool = True,
) -> list[tuple[int, float]]:
    """
    Find top-k chirp peaks while suppressing nearby duplicates.

    Parameters
    ----------
    x : np.ndarray
        Input signal.
    chirp_tpl : np.ndarray
        Chirp template.
    sr : int
        Sample rate.
    k : int
        Number of peaks to return.
    min_gap_s : float
        Minimum allowed gap between peaks in seconds.
    score_threshold : float
        Minimum correlation score to keep a peak.
    use_abs : bool
        Whether to use abs(correlation).

    Returns
    -------
    list[tuple[int, float]]
        Sorted list of (peak_idx, peak_score) by time.
    """
    corr = chirp_correlation(x, chirp_tpl, use_abs=use_abs)
    if len(corr) == 0 or k <= 0:
        return []

    min_gap = max(1, int(round(min_gap_s * sr)))
    used = np.zeros(len(corr), dtype=bool)
    peaks: list[tuple[int, float]] = []

    for _ in range(k):
        masked = np.where(used, -np.inf, corr)
        idx = int(np.argmax(masked))
        score = float(masked[idx])

        if not np.isfinite(score) or score < score_threshold:
            break

        peaks.append((idx, score))

        left = max(0, idx - min_gap)
        right = min(len(used), idx + min_gap)
        used[left:right] = True

    peaks.sort(key=lambda z: z[0])
    return peaks