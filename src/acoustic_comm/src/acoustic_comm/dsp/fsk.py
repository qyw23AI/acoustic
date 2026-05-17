from __future__ import annotations

import numpy as np

from .tone import tone


def tone_energy(x: np.ndarray, freq_hz: float, sr: int) -> float:
    """
    Measure tone energy at a target frequency using sin/cos projection:
    E = dot(x, sin)^2 + dot(x, cos)^2
    """
    n = len(x)
    if n == 0:
        return 0.0

    t = np.arange(n, dtype=np.float32) / float(sr)
    s = np.sin(2.0 * np.pi * float(freq_hz) * t).astype(np.float32)
    c = np.cos(2.0 * np.pi * float(freq_hz) * t).astype(np.float32)

    a = float(np.dot(x, s))
    b = float(np.dot(x, c))
    return a * a + b * b


def fsk_encode_bits(
    bits: list[int],
    sr: int,
    bit_dur: float,
    f0: float,
    f1: float,
    amp: float,
    fade_len: int = 0,
) -> np.ndarray:
    """
    2-FSK encode bits into waveform.
    bit=0 -> f0, bit=1 -> f1
    """
    if not bits:
        return np.zeros(0, dtype=np.float32)

    chunks = []
    for b in bits:
        freq = f1 if int(b) == 1 else f0
        chunks.append(tone(freq, bit_dur, sr, amp=amp, fade_len=fade_len))
    return np.concatenate(chunks).astype(np.float32)


def decide_bit(seg: np.ndarray, sr: int, f0: float, f1: float) -> int:
    """
    2-FSK decision by comparing energy at f0 and f1.
    Apply Hann window first to reduce spectral leakage.
    """
    if len(seg) == 0:
        return 0

    win = np.hanning(len(seg)).astype(np.float32)
    seg_w = np.asarray(seg, dtype=np.float32) * win

    e0 = tone_energy(seg_w, f0, sr)
    e1 = tone_energy(seg_w, f1, sr)
    return 1 if e1 > e0 else 0


def decode_bits_from(
    x: np.ndarray,
    start_idx: int,
    nbits: int,
    sr: int,
    bit_dur: float,
    f0: float,
    f1: float,
) -> list[int] | None:
    """
    Decode nbits from waveform starting at start_idx.
    Return None if the waveform is too short.
    """
    bit_len = int(round(bit_dur * sr))
    if bit_len <= 0:
        raise ValueError("bit_len must be positive")

    bits: list[int] = []
    for i in range(nbits):
        a = start_idx + i * bit_len
        b = a + bit_len
        seg = x[a:b]
        if len(seg) < bit_len:
            return None
        bits.append(decide_bit(seg, sr, f0, f1))

    return bits