from dataclasses import dataclass
from enum import Enum


class CommandTier(str, Enum):
    FAST = "fast"
    SLOW = "slow"


@dataclass(frozen=True)
class CommandSpec:
    alias: str
    text: str
    tier: CommandTier
    note: str = ""


CMD = {
    # 0x8A: "武馆：R2在端头等待，收到指令后开始拼接",

    0x8A: "R1播放音频后，R2立即放开矛头",
    0x5C: "武馆：拼接结束后判断成功，随后进行下一个端头动作",
    0x27: "武馆：R2接到R1离开武馆指令，在R1离开后进入树林",
    0xE1: "梅林：前三个梅林方块放好后，R1完全拿走，R2再上梅林",
    0x72: "梅林：肉眼判断R2拿够KFS，R1进入对抗区后，R2也离开梅林",
    0x39: "对抗区：R2站到R1上将KFS放在九宫格顶层",
    0x95: "全场：R2需要重试，由R1给出指令",
    0xC6: "全场：STOP/ABORT，立刻停下当前由声学触发的动作，进入等待状态",
}

CMD_SPEC = {
    # 0x8A: CommandSpec(
    #     alias="start_splice",
    #     text=CMD[0x8A],
    #     tier=CommandTier.FAST,
    #     note="流程推进类动作，优先低时延。",
    # ),

    0x8A: CommandSpec(
        alias="release_spear",
        text=CMD[0x8A],
        tier=CommandTier.FAST,
        note="释放矛头动作，要求低时延，使用 Fast 链路。",
    ),
    0x5C: CommandSpec(
        alias="next_terminal",
        text=CMD[0x5C],
        tier=CommandTier.SLOW,
        note="依赖确认后再进入下一步，建议更稳健。",
    ),
    0x27: CommandSpec(
        alias="enter_merlin",
        text=CMD[0x27],
        tier=CommandTier.FAST,
        note="流程推进类动作，优先低时延。",
    ),
    0xE1: CommandSpec(
        alias="climb_merlin",
        text=CMD[0xE1],
        tier=CommandTier.FAST,
        note="流程推进类动作，优先低时延。",
    ),
    0x72: CommandSpec(
        alias="leave_merlin",
        text=CMD[0x72],
        tier=CommandTier.FAST,
        note="阶段切换类动作，优先低时延。",
    ),
    0x39: CommandSpec(
        alias="place_on_top",
        text=CMD[0x39],
        tier=CommandTier.SLOW,
        note="高代价关键动作，建议强校验或更稳链路。",
    ),
    0x95: CommandSpec(
        alias="retry",
        text=CMD[0x95],
        tier=CommandTier.SLOW,
        note="异常恢复类动作，建议强校验或更稳链路。",
    ),
    0xC6: CommandSpec(
        alias="stop",
        text=CMD[0xC6],
        tier=CommandTier.SLOW,
        note="最高优先级安全命令。收到后应立即停下当前由声学触发的动作。",
    ),
}

ALIAS_TO_CMD = {
    spec.alias: cmd_id
    for cmd_id, spec in CMD_SPEC.items()
}


def cmd_name(cmd_id: int) -> str:
    return CMD.get(cmd_id, f"UNKNOWN(0x{cmd_id:02X})")


def cmd_spec(cmd_id: int) -> CommandSpec | None:
    return CMD_SPEC.get(cmd_id)


def cmd_alias(cmd_id: int) -> str:
    spec = cmd_spec(cmd_id)
    return spec.alias if spec is not None else f"unknown_{cmd_id:02X}".lower()


def cmd_id_from_alias(alias: str) -> int | None:
    return ALIAS_TO_CMD.get(alias.strip().lower())


def cmd_tier(cmd_id: int) -> str:
    spec = cmd_spec(cmd_id)
    return spec.tier.value if spec is not None else "unknown"


def cmd_note(cmd_id: int) -> str:
    spec = cmd_spec(cmd_id)
    return spec.note if spec is not None else ""


def is_fast_cmd(cmd_id: int) -> bool:
    spec = cmd_spec(cmd_id)
    return spec is not None and spec.tier == CommandTier.FAST


def is_slow_cmd(cmd_id: int) -> bool:
    spec = cmd_spec(cmd_id)
    return spec is not None and spec.tier == CommandTier.SLOW


def default_wav_name(cmd_id: int, mode: str | None = None) -> str:
    """
    Build a user-friendly default wav filename.

    Examples
    --------
    fast_start_splice.wav
    slow_place_on_top.wav
    legacy_start_splice.wav
    """
    alias = cmd_alias(cmd_id)
    if mode is None or mode == "auto":
        mode = cmd_tier(cmd_id)
    return f"{mode}_{alias}.wav"


FAST_CMD_IDS = tuple(
    cmd_id for cmd_id, spec in CMD_SPEC.items()
    if spec.tier == CommandTier.FAST
)

SLOW_CMD_IDS = tuple(
    cmd_id for cmd_id, spec in CMD_SPEC.items()
    if spec.tier == CommandTier.SLOW
)