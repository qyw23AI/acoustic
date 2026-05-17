from dataclasses import dataclass


@dataclass(frozen=True)
class AcousticConfig:
    """Shared acoustic protocol and waveform configuration."""

    # =========================
    # Audio
    # =========================
    sr: int = 16000
    amp: float = 0.35  # base waveform amplitude before final normalization

    # =========================
    # Chirp sync
    # =========================
    chirp_dur: float = 0.12
    chirp_f0: float = 1200.0
    chirp_f1: float = 3200.0

    # =========================
    # 2-FSK
    # =========================
    f0: float = 1500.0  # bit = 0
    f1: float = 2500.0  # bit = 1
    bit_dur: float = 0.05

    # Optional fade to reduce click/pop at segment boundaries
    fade_ms: float = 8.0

    # =========================
    # Frame format
    # =========================
    cmd_bits: int = 8
    seq_bits: int = 0
    crc_bits: int = 8
    msb_first: bool = True
    use_crc: bool = True

    # =========================
    # TX frame structure
    # =========================
    silence_head_s: float = 0.02  # silence before chirp
    silence_tail_s: float = 0.00  # silence after payload
    gap_s: float = 0.06           # silence between repeated frames
    repeat_n: int = 2

    # =========================
    # Helpers
    # =========================
    @property
    def payload_bits(self) -> int:
        return self.cmd_bits + self.seq_bits

    @property
    def frame_bits(self) -> int:
        return self.payload_bits + (self.crc_bits if self.use_crc else 0)

    @property
    def bit_len(self) -> int:
        return int(round(self.sr * self.bit_dur))

    @property
    def chirp_len(self) -> int:
        return int(round(self.sr * self.chirp_dur))

    @property
    def fade_len(self) -> int:
        return int(round(self.sr * self.fade_ms / 1000.0))

    @property
    def frame_bytes(self) -> int:
        bits = self.frame_bits
        if bits % 8 != 0:
            raise ValueError(f"frame_bits must be byte-aligned, got {bits}")
        return bits // 8


# 原始长链路，保留做兼容 / 回退
LEGACY_CONFIG = AcousticConfig(
    sr=16000,
    amp=0.35,
    chirp_dur=0.12,
    chirp_f0=1200.0,
    chirp_f1=3200.0,
    f0=1500.0,
    f1=2500.0,
    bit_dur=0.05,
    fade_ms=8.0,
    cmd_bits=8,
    seq_bits=8,
    crc_bits=8,
    msb_first=True,
    use_crc=True,
    silence_head_s=0.05,
    silence_tail_s=0.05,
    gap_s=0.10,
    repeat_n=3,
)

# 快动作链路：cmd
# [silence_head] + [chirp] + [cmd]
# one_frame + gap + one_frame
FAST_CONFIG = AcousticConfig(
    sr=16000,
    amp=0.35,
    chirp_dur=0.06,
    chirp_f0=1200.0,
    chirp_f1=3200.0,
    f0=1500.0,
    f1=2500.0,
    bit_dur=0.05,
    fade_ms=8.0,
    cmd_bits=8,
    seq_bits=0,
    crc_bits=0,
    msb_first=True,
    use_crc=False,
    silence_head_s=0.01,
    silence_tail_s=0.00,
    gap_s=0.02,
    repeat_n=2,
)

# 慢动作链路：cmd + crc
# [silence_head] + [chirp] + [cmd + crc]
# one_frame + gap + one_frame
SLOW_CONFIG = AcousticConfig(
    sr=16000,
    amp=0.35,
    chirp_dur=0.08,
    chirp_f0=1200.0,
    chirp_f1=3200.0,
    f0=1500.0,
    f1=2500.0,
    bit_dur=0.05,
    fade_ms=8.0,
    cmd_bits=8,
    seq_bits=0,
    crc_bits=8,
    msb_first=True,
    use_crc=True,
    silence_head_s=0.02,
    silence_tail_s=0.00,
    gap_s=0.06,
    repeat_n=2,
)

# 当前默认配置：先默认走慢链路，更稳
DEFAULT_CONFIG = SLOW_CONFIG