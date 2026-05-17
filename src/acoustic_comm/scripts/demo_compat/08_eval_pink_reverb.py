import numpy as np
from scipy.io.wavfile import read
from collections import Counter
from scipy.signal import chirp

# ===== 和第6课一致 =====
SR = 16000
CHIRP_DUR = 0.12
CHIRP_F0 = 1200
CHIRP_F1 = 3200
BIT_DUR = 0.05
F0 = 1500
F1 = 2500

REPEAT_N = 3
FRAME_BYTES = 3
FRAME_BITS = FRAME_BYTES * 8

TARGET_CMD = 13
TARGET_SEQ = 1

bit_len = int(BIT_DUR * SR)
chirp_len = int(CHIRP_DUR * SR)

SNR_LIST = [0, -5, -10, -15, -20, -25]
TRIALS = 30
RNG = np.random.default_rng(0)

# =======================
# 1) 生成粉噪：频域做 1/sqrt(f) 的 shaping
# =======================
def pink_noise(n, rng):
    # 频域构造
    X = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    freqs = np.fft.rfftfreq(n, d=1.0/SR)
    # 避免 f=0 除零
    scale = np.ones_like(freqs)
    scale[1:] = 1.0 / np.sqrt(freqs[1:])
    # 只对 rfft 的长度做 shaping
    Xr = np.fft.rfft(rng.standard_normal(n))
    Xr = Xr * scale
    x = np.fft.irfft(Xr, n=n).astype(np.float32)
    x = x / (np.max(np.abs(x)) + 1e-9)
    return x

def rms(x):
    return float(np.sqrt(np.mean(x*x) + 1e-12))

def add_pink_noise(clean, snr_db, rng):
    noise = pink_noise(len(clean), rng)
    clean_r = rms(clean)
    noise_r = rms(noise)
    target_noise_r = clean_r / (10 ** (snr_db / 20))
    noise = noise * (target_noise_r / (noise_r + 1e-12))
    mixed = clean + noise
    mixed = mixed / (np.max(np.abs(mixed)) + 1e-9) * 0.9
    return mixed.astype(np.float32)

# =======================
# 2) 简化混响：指数衰减的多回声 FIR
#    （不需要外部RIR数据集，但能模拟“拖尾+反射”）
# =======================
def make_simple_rir(sr, rt60_s=0.25, taps=12, max_delay_ms=60):
    """
    rt60_s: 混响衰减到很小的大致时间，越大越“空旷”
    taps:   回声个数
    max_delay_ms: 最长反射延迟
    """
    max_delay = int(max_delay_ms * sr / 1000)
    # 随机若干延迟点
    delays = np.sort(np.random.randint(0, max_delay, size=taps))
    # 指数衰减包络
    t = delays / sr
    # 让幅度按 e^{-t/tau} 衰减，tau 与 rt60 相关
    tau = rt60_s / 6.0
    amps = np.exp(-t / (tau + 1e-9))
    amps = amps / (np.sum(np.abs(amps)) + 1e-9)

    h = np.zeros(max_delay + 1, dtype=np.float32)
    h[0] = 1.0  # 直达声
    for d, a in zip(delays, amps):
        h[d] += 0.6 * a  # 0.6 控制混响强度
    return h

def apply_reverb(x, h):
    y = np.convolve(x, h, mode="full")[:len(x)]
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.9
    return y.astype(np.float32)

# =======================
# 3) CRC & 解码（同第7课）
# =======================
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

def tone_energy(x, freq_hz):
    n = len(x)
    t = np.arange(n) / SR
    s = np.sin(2*np.pi*freq_hz*t)
    c = np.cos(2*np.pi*freq_hz*t)
    a = float(np.dot(x, s))
    b = float(np.dot(x, c))
    return a*a + b*b

def decide_bit(seg):
    seg = seg * np.hanning(len(seg))
    e0 = tone_energy(seg, F0)
    e1 = tone_energy(seg, F1)
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

# =======================
# 4) 主评测：先混响，再加粉噪
# =======================
def main():
    clean_path = "06_tx.wav"
    sr, data = read(clean_path)
    if sr != SR:
        raise ValueError(f"采样率不一致：{sr} vs {SR}")
    clean = data.astype(np.float32) / 32768.0

    # 固定一个“房间”，否则每次 trial 的混响都变会不好比较
    np.random.seed(0)
    h = make_simple_rir(SR, rt60_s=0.35, taps=14, max_delay_ms=80)
    reverbed_clean = apply_reverb(clean, h)

    print("=== 第8课：混响(rt60≈0.35s)+粉噪 的 SNR 扫描评测 ===")
    print(f"目标：cmd={TARGET_CMD}, seq={TARGET_SEQ}, repeat={REPEAT_N}")
    print(f"SNR: {SNR_LIST} | trials={TRIALS}")
    print("-" * 74)

    for snr_db in SNR_LIST:
        ok = 0
        for _ in range(TRIALS):
            mixed = add_pink_noise(reverbed_clean, snr_db, RNG)
            if run_once(mixed):
                ok += 1
        print(f"SNR={snr_db:>3} dB | 成功 {ok:>2}/{TRIALS} | 成功率={ok/TRIALS:.2f}")

    print("-" * 74)
    print("提示：如果成功率仍然太高，下一课我们会再加“频率偏移/采样偏差”来逼近真实设备。")

if __name__ == "__main__":
    main()