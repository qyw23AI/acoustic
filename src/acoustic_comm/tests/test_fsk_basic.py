import numpy as np

from acoustic_comm.dsp.fsk import decode_bits_from, fsk_encode_bits
from acoustic_comm.protocol.constants import DEFAULT_CONFIG


def test_fsk_encode_returns_float32():
    cfg = DEFAULT_CONFIG
    bits = [1, 0, 1, 1, 0]

    x = fsk_encode_bits(
        bits=bits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
        amp=cfg.amp,
        fade_len=cfg.fade_len,
    )

    assert isinstance(x, np.ndarray)
    assert x.dtype == np.float32
    assert len(x) == len(bits) * cfg.bit_len


def test_fsk_roundtrip_basic():
    cfg = DEFAULT_CONFIG
    bits = [1, 0, 1, 0, 0, 1, 1, 0]

    x = fsk_encode_bits(
        bits=bits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
        amp=cfg.amp,
        fade_len=cfg.fade_len,
    )

    decoded = decode_bits_from(
        x=x,
        start_idx=0,
        nbits=len(bits),
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
    )

    assert decoded == bits


def test_fsk_roundtrip_with_leading_silence():
    cfg = DEFAULT_CONFIG
    bits = [0, 1, 0, 1, 1, 0]
    lead = np.zeros(cfg.bit_len * 2, dtype=np.float32)

    payload = fsk_encode_bits(
        bits=bits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
        amp=cfg.amp,
        fade_len=cfg.fade_len,
    )

    x = np.concatenate([lead, payload]).astype(np.float32)

    decoded = decode_bits_from(
        x=x,
        start_idx=len(lead),
        nbits=len(bits),
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
    )

    assert decoded == bits


def test_decode_bits_from_returns_none_when_too_short():
    cfg = DEFAULT_CONFIG
    bits = [1, 0, 1, 1]

    x = fsk_encode_bits(
        bits=bits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
        amp=cfg.amp,
        fade_len=cfg.fade_len,
    )

    # ask for one extra bit
    decoded = decode_bits_from(
        x=x,
        start_idx=0,
        nbits=len(bits) + 1,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
    )

    assert decoded is None


def test_fsk_roundtrip_without_fade():
    cfg = DEFAULT_CONFIG
    bits = [1, 1, 0, 0, 1, 0, 1, 0]

    x = fsk_encode_bits(
        bits=bits,
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
        amp=cfg.amp,
        fade_len=0,
    )

    decoded = decode_bits_from(
        x=x,
        start_idx=0,
        nbits=len(bits),
        sr=cfg.sr,
        bit_dur=cfg.bit_dur,
        f0=cfg.f0,
        f1=cfg.f1,
    )

    assert decoded == bits