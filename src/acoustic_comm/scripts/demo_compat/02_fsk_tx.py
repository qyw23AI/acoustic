import numpy as np
from scipy.io.wavfile import write

# ======================
# 1) 基本参数（先别改）
# ======================
sr = 16000           # 采样率
bit_dur = 0.05       # 每个bit持续时间(秒) 50ms
f0 = 1500            # 表示 bit=0 的频率
f1 = 2500            # 表示 bit=1 的频率
volume = 0.35        # 音量（0~1之间，先别太大）

# ======================
# 2) 工具函数：生成纯音
# ======================
def tone(freq_hz, duration_s, sr, volume):
    t = np.arange(int(sr * duration_s)) / sr
    return (volume * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)

def silence(duration_s, sr):
    return np.zeros(int(sr * duration_s), dtype=np.float32)

# ======================
# 3) 把整数转成bit序列
#    例如 13 -> 00001101 (8 bit)
# ======================
def int_to_bits(x, nbits=8):
    # 高位在前（MSB first）
    bits = [(x >> (nbits - 1 - i)) & 1 for i in range(nbits)]
    return bits

# ======================
# 4) 2-FSK 发射：0用f0，1用f1
# ======================
def fsk_encode_bits(bits):
    chunks = []
    for b in bits:
        freq = f1 if b == 1 else f0
        chunks.append(tone(freq, bit_dur, sr, volume))
    return np.concatenate(chunks)

# ======================
# 5) 生成一条“帧”（先最简单）
#    结构：静音(0.2s) + preamble(10101010) + payload(一个字节) + 静音(0.2s)
# ======================
preamble = [1,0,1,0,1,0,1,0]     # 先用最简单的交替序列当“前导”
payload_value = 13              # 你可以改成 0~255 的任何数
payload_bits = int_to_bits(payload_value, 8)

bits = preamble + payload_bits

wave = np.concatenate([
    silence(0.2, sr),
    fsk_encode_bits(bits),
    silence(0.2, sr),
])

# 防止爆音：再做一次归一化
wave = wave / (np.max(np.abs(wave)) + 1e-9) * 0.9

# 写 wav（16-bit PCM）
wav_int16 = (wave * 32767).astype(np.int16)
write("02_fsk_tx.wav", sr, wav_int16)

print("已生成：02_fsk_tx.wav")
print("payload =", payload_value)
print("payload bits =", "".join(str(b) for b in payload_bits))
