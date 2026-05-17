import numpy as np
from scipy.io.wavfile import read

# ======================
# 1) 这些参数必须和发射端一致
# ======================
sr_expected = 16000
bit_dur = 0.05
f0 = 1500
f1 = 2500

# 你发射端的帧：前面有 0.2s 静音，然后 preamble(8bit)，再 payload(8bit)，最后 0.2s 静音
silence_head_s = 0.2
preamble_bits = [1,0,1,0,1,0,1,0]
payload_nbits = 8

# ======================
# 2) 一个“测能量”的小工具：看某个频率在这一段里有多强
#    思路：把这一段跟 sin/cos 投影，能量越大说明这个频率越像
# ======================
def tone_energy(x, freq_hz, sr):
    n = len(x)
    t = np.arange(n) / sr
    s = np.sin(2 * np.pi * freq_hz * t)
    c = np.cos(2 * np.pi * freq_hz * t)
    # 投影（相当于只算这个频率的“相关能量”）
    a = np.dot(x, s)
    b = np.dot(x, c)
    return a*a + b*b

# ======================
# 3) 读取 wav
# ======================
wav_path = "02_fsk_tx.wav"
sr, data = read(wav_path)

if sr != sr_expected:
    raise ValueError(f"采样率不一致：文件sr={sr}，期望sr={sr_expected}")

# int16 -> float32 [-1, 1]
x = data.astype(np.float32) / 32768.0

# ======================
# 4) 切到真正的比特段（跳过开头静音）
# ======================
start = int(silence_head_s * sr)
x = x[start:]

# 每个bit多少个采样点
bit_len = int(bit_dur * sr)

# ======================
# 5) 逐bit判决：比 f0 能量大就是0，比 f1 能量大就是1（反过来）
# ======================
def decode_bits(x, nbits, sr, bit_len):
    bits = []
    for i in range(nbits):
        seg = x[i*bit_len : (i+1)*bit_len]
        # 加个“窗”让频谱更干净（可理解为减少边缘突变）
        w = np.hanning(len(seg))
        seg = seg * w

        e0 = tone_energy(seg, f0, sr)
        e1 = tone_energy(seg, f1, sr)
        bit = 1 if e1 > e0 else 0
        bits.append(bit)
    return bits

# 总共要解：preamble(8) + payload(8)
total_bits = len(preamble_bits) + payload_nbits
rx_bits = decode_bits(x, total_bits, sr, bit_len)

rx_preamble = rx_bits[:len(preamble_bits)]
rx_payload = rx_bits[len(preamble_bits):]

# ======================
# 6) payload bits -> int（高位在前）
# ======================
payload = 0
for b in rx_payload:
    payload = (payload << 1) | b

print("解码结果：")
print("rx preamble =", "".join(str(b) for b in rx_preamble))
print("rx payload  =", "".join(str(b) for b in rx_payload))
print("payload int =", payload)

# 给个简单检查
if rx_preamble != preamble_bits:
    print("⚠️ 警告：preamble 不匹配（后面我们会用更稳的同步方式解决）")