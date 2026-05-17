from acoustic_comm.protocol.constants import DEFAULT_CONFIG
from acoustic_comm.protocol.frame import (
    bits_to_bytes,
    bytes_to_bits,
    check_frame,
    pack_frame,
)


def test_pack_frame_with_crc_length():
    cfg = DEFAULT_CONFIG
    frame = pack_frame(0x8A, 0x01, cfg)
    assert isinstance(frame, bytes)
    assert len(frame) == 3


def test_pack_frame_without_crc_length():
    cfg = DEFAULT_CONFIG.__class__(use_crc=False)
    frame = pack_frame(0x8A, 0x01, cfg)
    assert isinstance(frame, bytes)
    assert len(frame) == 2


def test_frame_roundtrip_with_crc():
    cfg = DEFAULT_CONFIG
    cmd = 0x8A
    seq = 0x01

    frame = pack_frame(cmd, seq, cfg)
    bits = bytes_to_bits(frame, msb_first=cfg.msb_first)
    frame2 = bits_to_bytes(bits, msb_first=cfg.msb_first)

    ok, cmd2, seq2 = check_frame(frame2, cfg)

    assert frame2 == frame
    assert ok is True
    assert cmd2 == cmd
    assert seq2 == seq


def test_frame_roundtrip_without_crc():
    cfg = DEFAULT_CONFIG.__class__(use_crc=False)
    cmd = 0x27
    seq = 0x05

    frame = pack_frame(cmd, seq, cfg)
    bits = bytes_to_bits(frame, msb_first=cfg.msb_first)
    frame2 = bits_to_bytes(bits, msb_first=cfg.msb_first)

    ok, cmd2, seq2 = check_frame(frame2, cfg)

    assert frame2 == frame
    assert ok is True
    assert cmd2 == cmd
    assert seq2 == seq


def test_check_frame_rejects_bad_crc():
    cfg = DEFAULT_CONFIG
    frame = bytearray(pack_frame(0x8A, 0x01, cfg))

    # corrupt crc byte
    frame[-1] ^= 0x01

    ok, cmd, seq = check_frame(bytes(frame), cfg)
    assert ok is False
    assert cmd == 0x8A
    assert seq == 0x01


def test_check_frame_rejects_wrong_length_with_crc():
    cfg = DEFAULT_CONFIG
    ok, cmd, seq = check_frame(bytes([0x8A, 0x01]), cfg)
    assert ok is False
    assert cmd == 0
    assert seq == 0


def test_check_frame_rejects_wrong_length_without_crc():
    cfg = DEFAULT_CONFIG.__class__(use_crc=False)
    ok, cmd, seq = check_frame(bytes([0x8A]), cfg)
    assert ok is False
    assert cmd == 0
    assert seq == 0


def test_bytes_to_bits_and_back_identity():
    cfg = DEFAULT_CONFIG
    raw = bytes([0x8A, 0x5C, 0x27])
    bits = bytes_to_bits(raw, msb_first=cfg.msb_first)
    out = bits_to_bytes(bits, msb_first=cfg.msb_first)
    assert out == raw