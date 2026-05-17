from __future__ import annotations

from .constants import AcousticConfig
from .crc import crc8_atm


def int_to_bits(x: int, nbits: int = 8, msb_first: bool = True) -> list[int]:
    """Convert int to a list of bits."""
    if nbits <= 0:
        raise ValueError("nbits must be positive")
    if x < 0 or x >= (1 << nbits):
        raise ValueError(f"value {x} does not fit in {nbits} bits")

    if msb_first:
        return [(x >> (nbits - 1 - i)) & 1 for i in range(nbits)]
    return [(x >> i) & 1 for i in range(nbits)]


def bits_to_int(bits: list[int], msb_first: bool = True) -> int:
    """Convert a list of bits to int."""
    v = 0
    if msb_first:
        for b in bits:
            v = (v << 1) | (int(b) & 1)
    else:
        for i, b in enumerate(bits):
            v |= (int(b) & 1) << i
    return v


def bytes_to_bits(data: bytes, msb_first: bool = True) -> list[int]:
    """Convert bytes to bits."""
    out: list[int] = []
    for b in data:
        out.extend(int_to_bits(b, 8, msb_first=msb_first))
    return out


def bits_to_bytes(bits: list[int], msb_first: bool = True) -> bytes:
    """Convert bits to bytes. Length must be a multiple of 8."""
    if len(bits) % 8 != 0:
        raise ValueError("bits length must be multiple of 8")

    out = bytearray()
    for i in range(0, len(bits), 8):
        out.append(bits_to_int(bits[i:i + 8], msb_first=msb_first))
    return bytes(out)


def _validate_cfg(cfg: AcousticConfig) -> None:
    """Validate supported byte-aligned protocol field widths."""
    if cfg.cmd_bits != 8:
        raise ValueError(f"unsupported cmd_bits={cfg.cmd_bits}, expected 8")

    if cfg.seq_bits not in (0, 8):
        raise ValueError(f"unsupported seq_bits={cfg.seq_bits}, expected 0 or 8")

    if cfg.use_crc:
        if cfg.crc_bits != 8:
            raise ValueError(
                f"unsupported crc_bits={cfg.crc_bits}, expected 8 when CRC is enabled"
            )
    else:
        if cfg.crc_bits != 0:
            raise ValueError(
                f"unsupported crc_bits={cfg.crc_bits}, expected 0 when CRC is disabled"
            )


def _seq_enabled(cfg: AcousticConfig) -> bool:
    return cfg.seq_bits == 8


def _crc_enabled(cfg: AcousticConfig) -> bool:
    return cfg.use_crc and cfg.crc_bits == 8


def pack_frame(cmd_id: int, seq: int, cfg: AcousticConfig) -> bytes:
    """
    Build frame bytes.

    Supported protocol variants:
      1) cmd
      2) cmd + crc
      3) cmd + seq
      4) cmd + seq + crc

    Notes
    -----
    - cmd is always 1 byte
    - seq is included only when seq_bits == 8
    - crc is included only when use_crc is True and crc_bits == 8
    - when seq is disabled, the input `seq` argument is ignored
    """
    _validate_cfg(cfg)

    if not (0 <= cmd_id <= 0xFF):
        raise ValueError(f"cmd_id out of range: {cmd_id}")

    if _seq_enabled(cfg):
        if not (0 <= seq <= 0xFF):
            raise ValueError(f"seq out of range: {seq}")
        payload = bytes([cmd_id, seq])
    else:
        payload = bytes([cmd_id])

    if _crc_enabled(cfg):
        crc = crc8_atm(payload)
        return payload + bytes([crc])

    return payload


def check_frame(frame: bytes, cfg: AcousticConfig) -> tuple[bool, int, int]:
    """
    Verify a frame and return (ok, cmd, seq).

    Conventions
    -----------
    - cmd is always returned
    - when seq is disabled, returned seq is 0
    """
    _validate_cfg(cfg)

    seq_enabled = _seq_enabled(cfg)
    crc_enabled = _crc_enabled(cfg)

    expected_len = 1 + (1 if seq_enabled else 0) + (1 if crc_enabled else 0)
    if len(frame) != expected_len:
        return False, 0, 0

    cmd = frame[0]
    seq = frame[1] if seq_enabled else 0

    if crc_enabled:
        rx_crc = frame[-1]
        calc_crc = crc8_atm(frame[:-1])
        return calc_crc == rx_crc, cmd, seq

    return True, cmd, seq