import numpy as np
from scipy.signal import chirp
from collections import Counter

# ====== 和第6课一致的参数 ======
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

bit_len = int(BIT_DUR * SR)
chirp_len = int(CHIRP_DUR * SR)

# ====== 本课评测设置 ======
TEST_SECONDS = 60          # 测 60 秒；你可以改成 300 秒（5分钟）
RNG = np.random.default_rng(0)

# “触发判定”：投票至少需要多少票才算触发
VOTE_MIN = 2  # 3次重发里至少2票一致才触发（更安全）

# chirp 检测门限：越高越不容易误触发，但也可能漏检
CHIRP_THRESH = 0.20  # 经验值；如果误触发多就调高，比如0.30

# 扫描步长：越小越容易误触发（也更敏感）
SCAN_HOP_S = 0.02    # 每 20ms 检查一次候选点


# =======================
# 1) 噪声生成（粉噪更像环境）
# =======================
def pink_noise(n, rng):
    freqs = np.fft.rfftfreq(n, d=1.0/SR)
    scale = np.ones_like(freqs)
    scale[1:] = 1.0 / np.sqrt(freqs[1:])
    Xr = np.fft.rfft(rng.standard_normal(n))
    Xr *= scale
    x = np.fft.irfft(Xr, n=n).astype(np.float32)
    x = x / (np.max(np.abs(x)) + 1e-9)
    return x

def make_noise(seconds=60, kind="pink"):
    n = int(seconds * SR)
    if kind == "white":
        x = RNG.standard_normal(n).astype(np.float32)
        x = x / (np.max(np.abs(x)) + 1e-9)
    else:
        x = pink_noise(n, RNG)
    # 控制音量
    return (x * 0.6).astype(np.float32)

# =======================
# 2) CRC-8/ATM
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

# =======================
# 3) 2-FSK 解码（用你第10课的“扫频判决”）
# =======================
def tone_energy(x, freq_hz):
    n = len(x)
    t = np.arange(n) / SR
    s = np.sin(2*np.pi*freq_hz*t)
    c = np.cos(2*np.pi*freq_hz*t)
    a = float(np.dot(x, s))
    b = float(np.dot(x, c))
    return a*a + b*b

def max_energy_around(seg, f_center, span_hz=160, step_hz=20):
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

# =======================
# 4) chirp 模板 + 快速相关评分
# =======================
def make_chirp_template():
    t = np.arange(chirp_len) / SR
    tpl = chirp(t, f0=CHIRP_F0, f1=CHIRP_F1, t1=CHIRP_DUR, method="linear").astype(np.float32)
    tpl = tpl / (np.linalg.norm(tpl) + 1e-9)
    return tpl

TPL = make_chirp_template()

def chirp_score(x, start):
    seg = x[start:start+chirp_len]
    if len(seg) < chirp_len:
        return 0.0
    seg = seg / (np.linalg.norm(seg) + 1e-9)
    return float(np.dot(seg, TPL))

# =======================
# 5) 主：在纯噪声上扫，统计误触发
# =======================
def main():
    x = make_noise(TEST_SECONDS, kind="pink")
    hop = int(SCAN_HOP_S * SR)

    crc_pass = 0
    triggers = 0

    # 为了避免一个误峰连续触发多次：设置冷却时间
    cooldown_s = 0.5
    cooldown = 0

    i = 0
    while i + chirp_len + FRAME_BITS*bit_len < len(x):
        if cooldown > 0:
            cooldown -= hop
            i += hop
            continue

        score = chirp_score(x, i)
        if score >= CHIRP_THRESH:
            # 命中一个疑似 chirp，尝试解 3 帧（模拟 repeat）
            decoded = []
            base = i + chirp_len

            # 在噪声里我们不知道repeat的真实间隔，这里用“就地取3帧”
            # 目的：只要存在“伪造出来的合法帧”，就算误触发风险
            for r in range(REPEAT_N):
                start_bits = base + r * (FRAME_BITS * bit_len)
                bits = decode_bits_from(x, start_bits, FRAME_BITS)
                if bits is None:
                    continue
                frame = bits_to_bytes(bits)
                cmd, seq, crc = frame[0], frame[1], frame[2]
                if crc == crc8_atm(frame[:2]):
                    crc_pass += 1
                    decoded.append((cmd, seq))

            if decoded:
                winner, cnt = Counter(decoded).most_common(1)[0]
                if cnt >= VOTE_MIN:
                    triggers += 1
                    print(f"⚠️ 误触发：t={i/SR:.2f}s  score={score:.2f}  cmd={winner[0]} seq={winner[1]} 票数={cnt}")
                    cooldown = int(cooldown_s * SR)

        i += hop

    print("=== 第11课：误触发率评测 ===")
    print(f"测试时长：{TEST_SECONDS}s  噪声：pink  hop={SCAN_HOP_S}s  chirp_thresh={CHIRP_THRESH}")
    print(f"CRC通过帧数：{crc_pass}")
    print(f"最终触发次数：{triggers}")
    print("理想结果：最终触发次数 = 0")

if __name__ == "__main__":
    main()