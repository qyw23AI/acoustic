import numpy as np
from scipy.io.wavfile import read, write
from scipy.signal import chirp
from collections import Counter

# ========== 参数（和第6课保持一致） ==========
SR = 16000

CHIRP_DUR = 0.12
CHIRP_F0 = 1200
CHIRP_F1 = 3200
BIT_DUR = 0.05
F0 = 1500
F1 = 2500

REPEAT_N = 3
FRAME_BYTES = 3            # cmd(1) + seq(1) + crc(1)
FRAME_BITS = FRAME_BYTES * 8

TARGET_CMD = 13
TARGET_SEQ = 1

# 评测设置
SNR_LIST = [0, -5, -10, -15, -20, -25]
TRIALS = 30
RNG = np.random.default_rng(0)

bit_len = int(BIT_DUR * SR)
chirp_len = int(CHIRP_DUR * SR)

# ========== 基础：RMS / 加噪 ==========
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

# ========== CRC-8/ATM ==========
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

# ========== 2-FSK 解码 ==========
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

# ========== chirp 同步：相关找峰 ==========
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

# ========== 单次试验：返回是否成功 ==========
def run_once(wave):
    # 1) 找到最多 3 个 chirp 起点
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
        crc_calc = crc8_atm(frame[:2])
        if crc == crc_calc:
            decoded.append((cmd, seq))

    if not decoded:
        return False  # 没有任何CRC通过

    winner, cnt = Counter(decoded).most_common(1)[0]
    cmd, seq = winner
    return (cmd == TARGET_CMD) and (seq == TARGET_SEQ)

# ========== 主评测 ==========
def main():
    clean_path = "06_tx.wav"
    sr, data = read(clean_path)
    if sr != SR:
        raise ValueError(f"采样率不一致：{sr} vs {SR}")
    clean = data.astype(np.float32) / 32768.0

    print("=== 第7课：chirp+CRC+投票 的 SNR 扫描评测（白噪声）===")
    print(f"目标：cmd={TARGET_CMD}, seq={TARGET_SEQ}, repeat={REPEAT_N}")
    print(f"SNR: {SNR_LIST} | trials={TRIALS}")
    print("-" * 72)

    for snr_db in SNR_LIST:
        ok = 0
        for _ in range(TRIALS):
            mixed = add_white_noise(clean, snr_db, RNG)
            if run_once(mixed):
                ok += 1

        print(f"SNR={snr_db:>3} dB | 成功 {ok:>2}/{TRIALS} | 成功率={ok/TRIALS:.2f}")

        # 保存样例
        example = add_white_noise(clean, snr_db, RNG)
        write(f"07_eval_noisy_{snr_db}dB.wav", SR, (example * 32767).astype(np.int16))

    print("-" * 72)
    print("已保存 07_eval_noisy_XXdB.wav（每个 SNR 一条样例）")

if __name__ == "__main__":
    main()