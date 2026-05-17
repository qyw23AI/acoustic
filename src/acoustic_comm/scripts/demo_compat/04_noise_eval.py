import numpy as np
from scipy.io.wavfile import read, write

# ======================
# 0) 参数：必须和 TX/RX 一致
# ======================
SR = 16000
BIT_DUR = 0.05
F0 = 1500
F1 = 2500

SILENCE_HEAD_S = 0.2
PREAMBLE_BITS = [1, 0, 1, 0, 1, 0, 1, 0]
PAYLOAD_NBITS = 8
TARGET_PAYLOAD = 13

# 评测设置
# SNR_LIST = [25, 20, 15, 10, 5, 0, -5]
SNR_LIST = [0, -5, -10, -15, -20, -25]
TRIALS = 30
RNG = np.random.default_rng(0)

# ======================
# 1) 基础工具
# ======================
def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x) + 1e-12))

def bits_to_int(bits):
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v

# ======================
# 2) “测某频率能量” + 逐bit判决（2-FSK 解调）
# ======================
def tone_energy(x: np.ndarray, freq_hz: float, sr: int) -> float:
    n = len(x)
    t = np.arange(n) / sr
    s = np.sin(2 * np.pi * freq_hz * t)
    c = np.cos(2 * np.pi * freq_hz * t)
    a = float(np.dot(x, s))
    b = float(np.dot(x, c))
    return a * a + b * b

def decode_bits_from(x: np.ndarray, start_idx: int, nbits: int, sr: int, bit_len: int):
    bits = []
    for i in range(nbits):
        seg = x[start_idx + i * bit_len : start_idx + (i + 1) * bit_len]
        if len(seg) < bit_len:
            return None
        seg = seg * np.hanning(len(seg))
        e0 = tone_energy(seg, F0, sr)
        e1 = tone_energy(seg, F1, sr)
        bits.append(1 if e1 > e0 else 0)
    return bits

def decode_payload_fixed_start(wave: np.ndarray, sr: int):
    """当前版本：假设起点已知（跳过固定 0.2s 静音）。后面第6课会改成自动同步。"""
    start = int(SILENCE_HEAD_S * sr)
    bit_len = int(BIT_DUR * sr)
    total_bits = len(PREAMBLE_BITS) + PAYLOAD_NBITS

    rx_bits = decode_bits_from(wave, start, total_bits, sr, bit_len)
    if rx_bits is None:
        return None

    rx_pre = rx_bits[:len(PREAMBLE_BITS)]
    rx_pay = rx_bits[len(PREAMBLE_BITS):]
    payload = bits_to_int(rx_pay)
    return rx_pre, rx_pay, payload

# ======================
# 3) 加白噪声（按 SNR）
# ======================
def add_white_noise(clean: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    noise = rng.standard_normal(len(clean)).astype(np.float32)

    clean_r = rms(clean)
    noise_r = rms(noise)
    target_noise_r = clean_r / (10 ** (snr_db / 20))
    noise = noise * (target_noise_r / (noise_r + 1e-12))

    mixed = clean + noise
    mixed = mixed / (np.max(np.abs(mixed)) + 1e-9) * 0.9
    return mixed.astype(np.float32)

# ======================
# 4) 主流程：读文件 → 扫 SNR → 统计 → 保存样例
# ======================
def main():
    clean_path = "02_fsk_tx.wav"
    sr, data = read(clean_path)
    if sr != SR:
        raise ValueError(f"采样率不一致：文件sr={sr}，期望sr={SR}")

    clean = data.astype(np.float32) / 32768.0

    print("=== 第4课：2-FSK 白噪声 SNR 扫描评测（合并版）===")
    print(f"目标 payload: {TARGET_PAYLOAD}")
    print(f"SNR 列表: {SNR_LIST}")
    print(f"每档试验次数: {TRIALS}")
    print("-" * 68)

    for snr_db in SNR_LIST:
        pre_ok = 0
        ok = 0

        for _ in range(TRIALS):
            mixed = add_white_noise(clean, snr_db, RNG)
            out = decode_payload_fixed_start(mixed, sr)
            if out is None:
                continue
            rx_pre, rx_pay, payload = out

            if rx_pre == PREAMBLE_BITS:
                pre_ok += 1
            if (rx_pre == PREAMBLE_BITS) and (payload == TARGET_PAYLOAD):
                ok += 1

        print(f"SNR={snr_db:>3} dB | preamble命中 {pre_ok:>2}/{TRIALS} | 解码成功 {ok:>2}/{TRIALS}")

        # 每档保存一个样例（方便你听）
        example = add_white_noise(clean, snr_db, RNG)
        write(f"04_noisy_{snr_db}dB.wav", sr, (example * 32767).astype(np.int16))

    print("-" * 68)
    print("已保存 noisy_XXdB.wav（每个 SNR 一条样例，可直接播放对比）")

if __name__ == "__main__":
    main()