from __future__ import annotations

import argparse
from dataclasses import replace

from ..io.wav import write_wav
from ..protocol.codebook import (
    cmd_alias,
    cmd_id_from_alias,
    cmd_name,
    cmd_tier,
    default_wav_name,
)
from ..protocol.constants import (
    DEFAULT_CONFIG,
    FAST_CONFIG,
    LEGACY_CONFIG,
    SLOW_CONFIG,
    AcousticConfig,
)
from .build_waveform import build_tx_wave


def _parse_hex_byte(s: str) -> int:
    """
    Parse command byte from forms like:
      138
      0x8A
      8A
    """
    text = s.strip()
    if text.lower().startswith("0x"):
        v = int(text, 16)
    else:
        try:
            v = int(text, 10)
        except ValueError:
            v = int(text, 16)

    if not (0 <= v <= 0xFF):
        raise argparse.ArgumentTypeError(f"byte out of range: {s}")
    return v


def _parse_repeat(s: str) -> int:
    v = int(s)
    if v <= 0:
        raise argparse.ArgumentTypeError("repeat must be positive")
    return v


def _resolve_cmd(cmd: int | None, name: str | None) -> int:
    if cmd is not None:
        return cmd

    if name is None:
        raise ValueError("either --cmd or --name must be provided")

    cmd_id = cmd_id_from_alias(name)
    if cmd_id is None:
        raise ValueError(f"unknown command alias: {name}")

    return cmd_id


def _resolve_mode(mode: str, cmd_id: int) -> str:
    """
    Resolve final mode.

    auto:
      - fast cmd -> fast
      - slow cmd -> slow
    """
    mode = mode.lower()
    if mode == "auto":
        tier = cmd_tier(cmd_id)
        if tier in ("fast", "slow"):
            return tier
        raise ValueError(f"cannot auto-resolve mode for cmd=0x{cmd_id:02X}")

    return mode


def _pick_cfg(mode: str) -> AcousticConfig:
    mode = mode.lower()
    if mode == "default":
        return DEFAULT_CONFIG
    if mode == "fast":
        return FAST_CONFIG
    if mode == "slow":
        return SLOW_CONFIG
    if mode == "legacy":
        return LEGACY_CONFIG
    raise ValueError(f"unknown mode: {mode}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build TX acoustic waveform for one command."
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--cmd",
        type=_parse_hex_byte,
        help="command id, e.g. 0x8A",
    )
    group.add_argument(
        "--name",
        type=str,
        help="human-friendly command alias, e.g. start_splice",
    )

    parser.add_argument(
        "--seq",
        type=_parse_hex_byte,
        default=0,
        help="sequence byte (used only when seq_bits == 8; otherwise ignored)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["auto", "default", "fast", "slow", "legacy"],
        default="auto",
        help="which protocol config to use; auto maps by command tier",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="output wav path; if omitted, auto-generate a readable filename",
    )
    parser.add_argument(
        "--repeat",
        type=_parse_repeat,
        default=None,
        help="override repeat_n",
    )

    args = parser.parse_args()

    cmd_id = _resolve_cmd(args.cmd, args.name)
    final_mode = _resolve_mode(args.mode, cmd_id)
    cfg = _pick_cfg(final_mode)

    if args.repeat is not None:
        cfg = replace(cfg, repeat_n=args.repeat)

    out_path = args.out or default_wav_name(cmd_id, mode=final_mode)

    x = build_tx_wave(cmd_id, seq=args.seq, cfg=cfg)
    write_wav(out_path, x, cfg.sr)

    seq_info = args.seq if cfg.seq_bits == 8 else "ignored"
    print(
        f"Wrote {out_path} | "
        f"cmd=0x{cmd_id:02X} alias={cmd_alias(cmd_id)} "
        f"({cmd_name(cmd_id)}) "
        f"tier={cmd_tier(cmd_id)} "
        f"mode={final_mode} "
        f"seq={seq_info} "
        f"repeat={cfg.repeat_n} | "
        f"frame_bits={cfg.frame_bits} "
        f"duration={len(x) / cfg.sr:.3f}s sr={cfg.sr}"
    )


if __name__ == "__main__":
    main()