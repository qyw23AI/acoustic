import numpy as np
from scipy.io.wavfile import read
from scipy.signal import chirp

# ========== 参数（必须和 TX 一致） ==========
SR = 16000
CHIRP_DUR = 0.12
CHIRP_F0 = 1200
CHIRP_F1 = 3200

BIT_DUR = 0.05
F0 = 1500
F1 = 2500

# 帧格式：cmd(1B)+seq(1B)+crc(1B) => 24 bits
FRAME_BYTES = 3
FRAME_BITS = FRAME_BYTES * 8

# 解码窗口：chirp 后面紧跟数据
bit_len = int(BIT_DUR * SR)
chirp_len = int(CHIRP_DUR * SR)

# ========== CRC ==========
def crc8_atm(data_bytes: bytes) -> int:
    crc = 0x00
    for b in data_bytes:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) & 0xFF) ^ 0x07
            else:
                crc = (crc << 1) & 0xFF
    return crc

# ========== 频点能量判决（2-FSK） ==========
def tone_energy(x: np.ndarray, freq_hz: float, sr: int) -> float:
    n = len(x)
    t = np.arange(n) / sr
    s = np.sin(2*np.pi*freq_hz*t)
    c = np.cos(2*np.pi*freq_hz*t)
    a = float(np.dot(x, s))
    b = float(np.dot(x, c))
    return a*a + b*b

def decide_bit(seg: np.ndarray) -> int:
    seg = seg * np.hanning(len(seg))
    e0 = tone_energy(seg, F0, SR)
    e1 = tone_energy(seg, F1, SR)
    return 1 if e1 > e0 else 0

def decode_bits_from(x: np.ndarray, start_idx: int, nbits: int):
    bits = []
    for i in range(nbits):
        seg = x[start_idx + i*bit_len : start_idx + (i+1)*bit_len]
        if len(seg) < bit_len:
            return None
        bits.append(decide_bit(seg))
    return bits

def bits_to_bytes(bits):
    out = []
    for i in range(0, len(bits), 8):
        v = 0
        for b in bits[i:i+8]:
            v = (v << 1) | int(b)
        out.append(v)
    return bytes(out)

# ========== chirp 同步：做相关，找峰值 ==========
def make_chirp_template():
    t = np.arange(chirp_len) / SR
    tpl = chirp(t, f0=CHIRP_F0, f1=CHIRP_F1, t1=CHIRP_DUR, method="linear").astype(np.float32)
    # 归一化，相关更稳定
    tpl = tpl / (np.linalg.norm(tpl) + 1e-9)
    return tpl

def find_topk_chirp_peaks(x: np.ndarray, k=3, min_gap_s=0.25):
    tpl = make_chirp_template()
    # 相关：y[n] = sum x[n:n+L]*tpl
    corr = np.correlate(x, tpl, mode="valid")
    corr_abs = np.abs(corr)

    # 选 top-k 峰，但峰之间要隔开，避免同一帧附近重复选中
    min_gap = int(min_gap_s * SR)
    peaks = []
    used = np.zeros_like(corr_abs, dtype=bool)

    for _ in range(k):
        idx = np.argmax(np.where(used, -1.0, corr_abs))
        if corr_abs[idx] < 1e-6:
            break
        peaks.append(idx)
        # 屏蔽邻域
        left = max(0, idx - min_gap)
        right = min(len(used), idx + min_gap)
        used[left:right] = True

    return sorted(peaks)

# ========== 主流程：找到 3 个帧起点 -> 解码 -> CRC -> 投票 ==========
def main():
    wav_path = "06_tx.wav"
    sr, data = read(wav_path)
    if sr != SR:
        raise ValueError(f"采样率不一致：{sr} vs {SR}")
    x = data.astype(np.float32) / 32768.0

    # 找到可能的 3 个 chirp 起点（因为 TX 重复了3次）
    peaks = find_topk_chirp_peaks(x, k=3, min_gap_s=0.25)
    print("检测到 chirp 起点（samples）:", peaks)

    decoded = []
    for p in peaks:
        data_start = p + chirp_len  # chirp 后面就是数据
        bits = decode_bits_from(x, data_start, FRAME_BITS)
        if bits is None:
            continue
        frame = bits_to_bytes(bits)
        cmd, seq, crc = frame[0], frame[1], frame[2]
        crc_calc = crc8_atm(frame[:2])
        ok = (crc == crc_calc)
        print(f"frame@{p}: cmd={cmd}, seq={seq}, crc=0x{crc:02X}, calc=0x{crc_calc:02X}, ok={ok}")
        if ok:
            decoded.append((cmd, seq))

    if not decoded:
        print("❌ 没有任何 CRC 通过的帧，丢弃")
        return

    # 多数投票（cmd,seq 完全一致才算一票）
    from collections import Counter
    winner, cnt = Counter(decoded).most_common(1)[0]
    cmd, seq = winner
    print(f"✅ 投票结果：cmd={cmd}, seq={seq}（{cnt} 票）")

if __name__ == "__main__":
    main()