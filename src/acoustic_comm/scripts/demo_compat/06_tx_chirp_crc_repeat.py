import numpy as np
from scipy.io.wavfile import write
from scipy.signal import chirp

# ========== 参数 ==========
SR = 16000
VOLUME = 0.35

# chirp preamble
CHIRP_DUR = 0.12          # 120ms
CHIRP_F0 = 1200
CHIRP_F1 = 3200

# 2-FSK 数据
BIT_DUR = 0.05
F0 = 1500
F1 = 2500

# 帧结构： [silence][chirp][payload(1B)+seq(1B)+crc(1B)][silence]
SILENCE_HEAD_S = 0.05
SILENCE_TAIL_S = 0.05

REPEAT_N = 3
GAP_S = 0.10              # 每帧之间隔 100ms 静音

# 你要发的命令
CMD_ID = 13
SEQ = 1  # 你可以改，用于去重


def silence(dur_s):
    return np.zeros(int(SR * dur_s), dtype=np.float32)

def tone(freq_hz, dur_s, volume=VOLUME):
    t = np.arange(int(SR * dur_s)) / SR
    return (volume * np.sin(2*np.pi*freq_hz*t)).astype(np.float32)

def make_chirp():
    t = np.arange(int(SR * CHIRP_DUR)) / SR
    x = chirp(t, f0=CHIRP_F0, f1=CHIRP_F1, t1=CHIRP_DUR,
              method="linear").astype(np.float32)
    x = x * VOLUME
    return x

def int_to_bits(x, nbits=8):
    return [(x >> (nbits - 1 - i)) & 1 for i in range(nbits)]

def crc8_atm(data_bytes: bytes) -> int:
    """
    CRC-8/ATM (poly=0x07, init=0x00, xorout=0x00), 常见、实现简单
    """
    crc = 0x00
    for b in data_bytes:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) & 0xFF) ^ 0x07
            else:
                crc = (crc << 1) & 0xFF
    return crc

def fsk_encode_bits(bits):
    chunks = []
    for b in bits:
        chunks.append(tone(F1 if b == 1 else F0, BIT_DUR))
    return np.concatenate(chunks)

def build_frame(cmd_id: int, seq: int):
    payload = bytes([cmd_id & 0xFF, seq & 0xFF])
    crc = crc8_atm(payload)
    frame_bytes = payload + bytes([crc])

    bits = []
    for byte in frame_bytes:
        bits += int_to_bits(byte, 8)

    x = np.concatenate([
        silence(SILENCE_HEAD_S),
        make_chirp(),
        fsk_encode_bits(bits),
        silence(SILENCE_TAIL_S),
    ])
    return x, crc

def main():
    frame, crc = build_frame(CMD_ID, SEQ)

    # 重复发送 N 次
    gap = silence(GAP_S)
    x = np.concatenate([frame if i == 0 else np.concatenate([gap, frame]) for i in range(REPEAT_N)])

    # 防爆音
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.9

    write("06_tx.wav", SR, (x * 32767).astype(np.int16))
    print("已生成：06_tx.wav")
    print(f"CMD_ID={CMD_ID}, SEQ={SEQ}, CRC=0x{crc:02X}, repeat={REPEAT_N}")

if __name__ == "__main__":
    main()