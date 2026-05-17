from __future__ import annotations

import numpy as np

from ..dsp.chirp_sync import make_chirp
from ..dsp.fsk import fsk_encode_bits
from ..dsp.tone import silence
from ..protocol.constants import AcousticConfig
from ..protocol.frame import bytes_to_bits, pack_frame


def _normalize_peak(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    """
    Peak-normalize waveform to approximately [-peak, peak].
    """
    y = np.asarray(x, dtype=np.float32)
    if len(y) == 0:
        return y

    m = float(np.max(np.abs(y)))
    if m <= 1e-12:
        return y
    return (y / m * float(peak)).astype(np.float32)


def build_one_frame(cmd_id: int, seq: int = 0, cfg: AcousticConfig | None = None) -> np.ndarray:
    """
    Build one TX frame waveform.

    General structure:
      [silence_head] + [chirp] + [payload(FSK)] + [optional silence_tail]

    Notes
    -----
    - Actual payload bytes are determined by pack_frame(cmd_id, seq, cfg)
    - seq may be ignored when cfg.seq_bits == 0
    - silence_tail may be empty when cfg.silence_tail_s == 0
    """
    if cfg is None:
        raise ValueError("cfg must not be None")

    frame_bytes = pack_frame(cmd_id, seq, cfg)
    bits = bytes_to_bits(frame_bytes, msb_first=cfg.msb_first)

    fade_len = getattr(cfg, "fade_len", 0)

    chirp_x = make_chirp(
        sr=cfg.sr,
        chirp_dur=cfg.chirp_dur,
        f0=cfg.chirp_f0,
        f1=cfg.chirp_f1,
        amp=cfg.amp,
        fade_len=fade_len,
    )

    payload_x = fsk_encode_bits(
        bits=bits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
        amp=cfg.amp,
        fade_len=fade_len,
    )

    return np.concatenate(
        [
            silence(cfg.silence_head_s, cfg.sr),
            chirp_x,
            payload_x,
            silence(cfg.silence_tail_s, cfg.sr),
        ]
    ).astype(np.float32)


def build_tx_wave(
    cmd_id: int,
    seq: int = 0,
    cfg: AcousticConfig | None = None,
    normalize: bool = True,
) -> np.ndarray:
    """
    Build full repeated TX waveform.

    Repeat structure:
      one_frame + gap + one_frame + gap + ... + one_frame

    Notes
    -----
    - seq may be ignored when cfg.seq_bits == 0
    - gap may be empty when cfg.gap_s == 0
    """
    if cfg is None:
        raise ValueError("cfg must not be None")

    one = build_one_frame(cmd_id, seq=seq, cfg=cfg)

    if cfg.repeat_n <= 1:
        return _normalize_peak(one) if normalize else one

    gap = silence(cfg.gap_s, cfg.sr)

    chunks = []
    for i in range(cfg.repeat_n):
        chunks.append(one)
        if i != cfg.repeat_n - 1:
            chunks.append(gap)

    out = np.concatenate(chunks).astype(np.float32)
    return _normalize_peak(out) if normalize else out