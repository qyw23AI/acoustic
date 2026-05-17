import numpy as np
from scipy.io.wavfile import read

# ======================
# 0) 参数：必须和 TX 一致
# ======================
SR = 16000
BIT_DUR = 0.05
F0 = 1500
F1 = 2500

PREAMBLE_BITS = [1,0,1,0,1,0,1,0]
PAYLOAD_NBITS = 8
TARGET_PAYLOAD = 13  # 只是用来验证（你也可以不需要）

# 搜索设置：步长越小越稳，但越慢；先用 bit_len//4 是折中
SEARCH_STEP_DIV = 4

# ======================
# 1) 基础函数：测频点能量 + 判 bit
# ======================
def tone_energy(x: np.ndarray, freq_hz: float, sr: int) -> float:
    n = len(x)
    t = np.arange(n) / sr
    s = np.sin(2 * np.pi * freq_hz * t)
    c = np.cos(2 * np.pi * freq_hz * t)
    a = float(np.dot(x, s))
    b = float(np.dot(x, c))
    return a*a + b*b

def decide_bit(seg: np.ndarray, sr: int) -> int:
    seg = seg * np.hanning(len(seg))
    e0 = tone_energy(seg, F0, sr)
    e1 = tone_energy(seg, F1, sr)
    return 1 if e1 > e0 else 0

def decode_bits_from(x: np.ndarray, start_idx: int, nbits: int, sr: int, bit_len: int):
    bits = []
    for i in range(nbits):
        seg = x[start_idx + i*bit_len : start_idx + (i+1)*bit_len]
        if len(seg) < bit_len:
            return None
        bits.append(decide_bit(seg, sr))
    return bits

def bits_to_int(bits):
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v

# ======================
# 2) 关键：自动同步（在整段音频里找 preamble）
#    思路：滑动尝试每一个可能起点，解出8个bit，
#          看它和 PREAMBLE_BITS 有多像（匹配位数越多越好）
# ======================
def find_preamble_start(x: np.ndarray, sr: int, bit_len: int):
    pre_len = len(PREAMBLE_BITS)
    step = max(1, bit_len // SEARCH_STEP_DIV)

    best_score = -1
    best_start = None

    # 为了不扫到文件尾巴导致越界，这里留出 preamble 的长度
    max_start = len(x) - pre_len * bit_len
    for start in range(0, max_start, step):
        rx_pre = decode_bits_from(x, start, pre_len, sr, bit_len)
        if rx_pre is None:
            continue
        score = sum(int(a == b) for a, b in zip(rx_pre, PREAMBLE_BITS))
        if score > best_score:
            best_score = score
            best_start = start

            # 小优化：如果已经 8/8 全匹配，可以直接提前结束
            if best_score == pre_len:
                break

    return best_start, best_score

# ======================
# 3) 主流程：读 wav → 同步 → 解整帧
# ======================
def main():
    wav_path = "04_noisy_-10dB.wav"
    sr, data = read(wav_path)
    if sr != SR:
        raise ValueError(f"采样率不一致：文件sr={sr}，期望sr={SR}")

    x = data.astype(np.float32) / 32768.0
    bit_len = int(BIT_DUR * sr)
    total_bits = len(PREAMBLE_BITS) + PAYLOAD_NBITS

    start, score = find_preamble_start(x, sr, bit_len)

    print("=== 第5课：自动同步 ===")
    print("best preamble score =", score, "/", len(PREAMBLE_BITS))
    print("best start sample   =", start)

    if start is None:
        print("没找到 preamble（起点为 None）")
        return

    rx_bits = decode_bits_from(x, start, total_bits, sr, bit_len)
    rx_pre = rx_bits[:len(PREAMBLE_BITS)]
    rx_pay = rx_bits[len(PREAMBLE_BITS):]
    payload = bits_to_int(rx_pay)

    print("rx preamble =", "".join(map(str, rx_pre)))
    print("rx payload  =", "".join(map(str, rx_pay)))
    print("payload int =", payload)

    if payload == TARGET_PAYLOAD:
        print("✅ payload 与期望一致")
    else:
        print("⚠️ payload 与期望不一致（后面我们会用更强的 preamble + CRC + 重发投票来解决）")

if __name__ == "__main__":
    main()