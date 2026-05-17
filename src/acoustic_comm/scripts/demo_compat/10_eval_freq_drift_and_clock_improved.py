import numpy as np
from scipy.io.wavfile import read
from scipy.signal import chirp
from collections import Counter

# ===== 参数（同第6课）=====
SR = 16000
CHIRP_DUR = 0.12
CHIRP_F0 = 1200
CHIRP_F1 = 3200
BIT_DUR = 0.05

# 注意：这里“接收端”仍按固定 F0/F1 解码，频偏会让它变难
F0 = 1500
F1 = 2500

REPEAT_N = 3
FRAME_BYTES = 3
FRAME_BITS = FRAME_BYTES * 8

TARGET_CMD = 13
TARGET_SEQ = 1

bit_len = int(BIT_DUR * SR)
chirp_len = int(CHIRP_DUR * SR)

SNR_DB = 0       # 固定一个比较狠的噪声档（你可以改 0 或 -5）
TRIALS = 50
RNG = np.random.default_rng(0)

# ========= 工具：RMS/加白噪 =========
def rms(x):
    return float(np.sqrt(np.mean(x*x) + 1e-12))

def add_white_noise(clean, snr_db, rng):
    noise = rng.standard_normal(len(clean)).astype(np.float32)
    clean_r = rms(clean)
    noise_r = rms(noise)
    target_noise_r = clean_r / (10 ** (snr_db / 20))
    noise = noise * (target_noise_r / (noise_r + 1e-12))
    mixed = clean + noise
    mixed = mixed / (np.max(np.abs(mixed)) + 1e-9) * 0.9
    return mixed.astype(np.float32)

# ========= CRC-8/ATM =========
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

# ========= 2-FSK 能量判决 =========
def tone_energy(x, freq_hz):
    n = len(x)
    t = np.arange(n) / SR
    s = np.sin(2*np.pi*freq_hz*t)
    c = np.cos(2*np.pi*freq_hz*t)
    a = float(np.dot(x, s))
    b = float(np.dot(x, c))
    return a*a + b*b

def max_energy_around(seg, f_center, span_hz=160, step_hz=20):
    """
    在 f_center 附近扫一圈频率，取最大能量
    span_hz=160 表示扫 f_center±160Hz
    step_hz=20 表示每 20Hz 取一个点
    """
    best = 0.0
    for df in range(-span_hz, span_hz + 1, step_hz):
        e = tone_energy(seg, f_center + df)
        if e > best:
            best = e
    return best

def decide_bit(seg):
    seg = seg * np.hanning(len(seg))
    e0 = max_energy_around(seg, F0, span_hz=160, step_hz=20)
    e1 = max_energy_around(seg, F1, span_hz=160, step_hz=20)
    return 1 if e1 > e0 else 0

def decode_bits_from(x, start_idx, nbits):
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

# ========= chirp 同步 =========
def make_chirp_template():
    t = np.arange(chirp_len) / SR
    tpl = chirp(t, f0=CHIRP_F0, f1=CHIRP_F1, t1=CHIRP_DUR, method="linear").astype(np.float32)
    tpl = tpl / (np.linalg.norm(tpl) + 1e-9)
    return tpl

def find_topk_chirp_peaks(x, k=3, min_gap_s=0.25):
    tpl = make_chirp_template()
    corr = np.correlate(x, tpl, mode="valid")
    corr_abs = np.abs(corr)

    min_gap = int(min_gap_s * SR)
    used = np.zeros_like(corr_abs, dtype=bool)
    peaks = []

    for _ in range(k):
        idx = np.argmax(np.where(used, -1.0, corr_abs))
        if corr_abs[idx] < 1e-6:
            break
        peaks.append(int(idx))
        left = max(0, idx - min_gap)
        right = min(len(used), idx + min_gap)
        used[left:right] = True

    return sorted(peaks)

def run_once(wave):
    peaks = find_topk_chirp_peaks(wave, k=REPEAT_N, min_gap_s=0.25)
    decoded = []
    for p in peaks:
        data_start = p + chirp_len
        bits = decode_bits_from(wave, data_start, FRAME_BITS)
        if bits is None:
            continue
        frame = bits_to_bytes(bits)
        if len(frame) != 3:
            continue
        cmd, seq, crc = frame[0], frame[1], frame[2]
        if crc == crc8_atm(frame[:2]):
            decoded.append((cmd, seq))

    if not decoded:
        return False
    winner, _ = Counter(decoded).most_common(1)[0]
    return winner == (TARGET_CMD, TARGET_SEQ)

# ========= 核心：模拟“设备误差” =========
def time_stretch_linear(x, stretch):
    """
    stretch > 1: 变长（相当于采样率偏低）
    stretch < 1: 变短（相当于采样率偏高）
    用线性插值重采样（足够做压测）
    """
    n = len(x)
    new_n = int(n * stretch)
    xp = np.linspace(0, 1, n, endpoint=False)
    xq = np.linspace(0, 1, new_n, endpoint=False)
    y = np.interp(xq, xp, x).astype(np.float32)
    # 为了让后续算法不越界，我们裁/补回原长度
    if len(y) >= n:
        y = y[:n]
    else:
        y = np.pad(y, (0, n-len(y)))
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.9
    return y

def freq_shift_multiply(x, hz):
    """
    频移：用 cos/sin 乘法相当于搬移频谱（简化版压测）。
    注意：这是“工程压测手段”，不是完美的物理声学模型，但足以逼近问题。
    """
    n = len(x)
    t = np.arange(n) / SR
    c = np.cos(2*np.pi*hz*t).astype(np.float32)
    y = (x * c).astype(np.float32)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.9
    return y

def main():
    sr, data = read("06_tx.wav")
    if sr != SR:
        raise ValueError(f"采样率不一致：{sr} vs {SR}")
    clean = data.astype(np.float32) / 32768.0

    # 压测范围：采样率偏差（ppm 级）用 stretch 模拟
    # 例如 0.998 ~ 1.002 相当于 ±0.2%（这在设备上不算夸张）
    stretch_list = [0.998, 0.999, 1.000, 1.001, 1.002]

    # 频移范围：±0~120Hz（你可以扩大）
    freq_shift_list = [-120, -80, -40, 0, 40, 80, 120]

    print("=== 第10课：频偏 + 采样率偏差 压测 ===")
    print(f"固定噪声：白噪 SNR={SNR_DB} dB, trials={TRIALS}")
    print("stretch_list =", stretch_list)
    print("freq_shift_list(Hz) =", freq_shift_list)
    print("-" * 78)

    for stretch in stretch_list:
        row = []
        for df in freq_shift_list:
            ok = 0
            for _ in range(TRIALS):
                x = time_stretch_linear(clean, stretch)
                x = add_white_noise(x, SNR_DB, RNG)
                x = freq_shift_multiply(x, df)
                if run_once(x):
                    ok += 1
            row.append(ok / TRIALS)
        row_str = " ".join(f"{v:4.2f}" for v in row)
        print(f"stretch={stretch:.3f} | {row_str}   (df: {freq_shift_list})")

    print("-" * 78)
    print("解释：每行是一个采样率偏差(stretch)，每列是一个频偏(df Hz)下的成功率。")

if __name__ == "__main__":
    main()
