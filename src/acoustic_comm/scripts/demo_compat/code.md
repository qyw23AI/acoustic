01_make_beep.py
```
import numpy as np
from scipy.io.wavfile import write

# ① 采样率：每秒采多少个点（16000 是语音常用值）
sr = 16000

# ② 生成一个“正弦波”函数：就是纯音（像哨子声）
def tone(freq_hz, duration_s, sr, volume=0.3):
    t = np.arange(int(sr * duration_s)) / sr          # 时间轴：0, 1/sr, 2/sr, ...
    x = volume * np.sin(2 * np.pi * freq_hz * t)      # 正弦：振幅随时间变化
    return x.astype(np.float32)

# ③ 生成“静音”段：就是全 0
def silence(duration_s, sr):
    return np.zeros(int(sr * duration_s), dtype=np.float32)

# ④ 拼一个简单的“指令”：哔(0.2s) + 静(0.1s) + 哔(0.2s)
cmd = np.concatenate([
    tone(2000, 0.2, sr),      # 2000Hz 哔
    silence(0.1, sr),         # 0.1s 静音
    tone(2000, 0.2, sr)       # 再哔一次
])

# ⑤ 防止爆音：把波形限制在 [-1, 1] 以内
cmd = cmd / (np.max(np.abs(cmd)) + 1e-9) * 0.9

# ⑥ 写成 wav 文件（16-bit PCM），任何播放器都能播
wav_int16 = (cmd * 32767).astype(np.int16)
write("01_command_beep.wav", sr, wav_int16)

print("已生成：1. command_beep.wav")
```
02_fsk_tx.py
```
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
```
03_fsk_rx.py
```
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
```
04_noise_eval.py
```
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
```
05_sync_rx.py
```
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
```
06_rx_chirp_crc_vote.py
```
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
```
06_tx_chirp_crc_repeat.py
```
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
```
07_eval_chirp_crc_vote_noise.py
```
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
```
08_eval_pink_reverb.py
```
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
```
09_eval_freq_drift_and_clock.py
```
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

    print("=== 第9课：频偏 + 采样率偏差 压测 ===")
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
```
10_eval_freq_drift_and_clock_improved.py
```
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
```
11_false_alarm_test.py
```
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
```
12_false_alarm_test copy.py
```
import numpy as np
from scipy.io.wavfile import read
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
    sr, data = read("noise_16k.wav")
    if sr != SR:
        raise ValueError(f"采样率不一致：{sr} vs {SR}")
    x = data.astype(np.float32) / 32768.0
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

    print("=== 第12课：误触发率评测 ===")
    print(f"测试时长：{TEST_SECONDS}s  噪声：pink  hop={SCAN_HOP_S}s  chirp_thresh={CHIRP_THRESH}")
    print(f"CRC通过帧数：{crc_pass}")
    print(f"最终触发次数：{triggers}")
    print("理想结果：最终触发次数 = 0")

if __name__ == "__main__":
    main()
```
12_mix_tx_into_stadium.py
```
import numpy as np
from scipy.io.wavfile import read, write

SR = 16000

def to_f32(wav):
    if wav.dtype == np.int16:
        return wav.astype(np.float32) / 32768.0
    return wav.astype(np.float32)

def rms(x):
    return float(np.sqrt(np.mean(x*x) + 1e-12))

def mix_at_snr(noise, sig, snr_db):
    """
    把 sig 叠到 noise 上，使得叠加区域内信噪比约为 snr_db（以RMS计）
    """
    n = noise.copy()
    L = min(len(n), len(sig))
    n_seg = n[:L]
    s = sig[:L]

    rn = rms(n_seg)
    rs = rms(s)
    # 目标：rs_scaled / rn = 10^(snr/20)
    target_rs = rn * (10 ** (snr_db / 20))
    scale = target_rs / (rs + 1e-12)

    mixed = n.copy()
    mixed[:L] = n_seg + s * scale

    # 防爆音
    mixed = mixed / (np.max(np.abs(mixed)) + 1e-9) * 0.9
    return mixed.astype(np.float32), scale

def main():
    # 读观众噪声（30s）
    sr_n, n = read("noise_16k.wav")
    if sr_n != SR:
        raise ValueError(f"noise sr mismatch: {sr_n} vs {SR}")
    noise = to_f32(n)

    # 读指令（较短）
    sr_t, t = read("6. tx.wav")
    if sr_t != SR:
        raise ValueError(f"tx sr mismatch: {sr_t} vs {SR}")
    tx = to_f32(t)

    # 你可以改这几个档位：越小越难
    snr_list = [10, 5, 0, -5]

    for snr_db in snr_list:
        mixed, scale = mix_at_snr(noise, tx, snr_db)
        out = f"12B_stadium_mix_snr{snr_db}dB.wav"
        write(out, SR, (mixed * 32767).astype(np.int16))
        print(f"生成 {out}  (tx_scale={scale:.3f})")

    print("提示：你可以先播放这些wav，听听指令在欢呼里还能不能隐约听到。")

if __name__ == "__main__":
    main()
```
12_rx_chirp_crc_vote copy.py
```
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
    wav_path = "12B_stadium_mix_snr-5dB.wav"
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
```
13_A_mic_test.py
```
import sounddevice as sd
import numpy as np

SR = 16000
DUR = 3  # 录 3 秒

print("开始录音...")
audio = sd.rec(int(DUR * SR), samplerate=SR, channels=1, dtype="float32")
sd.wait()
audio = audio.reshape(-1)

print("录音完成")
print("采样点数:", len(audio))
print("最大幅度:", float(np.max(np.abs(audio))))
print("前 10 个采样:", audio[:10])
```
13_B_realtime_rx.py
```
# 13. B_realtime_rx.py  (FIXED: match TX frame + CRC + chirp template)
import time
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from scipy.signal import chirp
from collections import Counter

# =======================
# 参数（必须和 TX 一致）
# =======================
SR = 16000

CHIRP_DUR = 0.12
CHIRP_F0 = 1200
CHIRP_F1 = 3200

BIT_DUR = 0.05
F0 = 1500
F1 = 2500

# ✅ TX 是 1B cmd + 1B seq + 1B crc
CMD_BITS = 8
SEQ_BITS = 8
CRC_BITS = 8

REPEAT = 3
VOTE_MIN = 2

# 实时扫描参数
HOP_S = 0.02              # 每次推进 20ms
RING_S = 6.0              # ring buffer 保存最近 6 秒
MIN_GAP_S = 0.25          # chirp 起点至少间隔 0.25s
CHIRP_THRESH = 0.10       # 建议先用 0.15；如果检测不到再降到 0.12 / 0.10
COOLDOWN_S = 1.0          # 触发后 1 秒内不再触发

# 如果你有多个麦克风设备，可能需要指定输入设备
# 用 sd.query_devices() 找到对应设备编号，填到这里；不填就用系统默认
INPUT_DEVICE = None  # 例如 2；不确定就先 None


# =======================
# 工具函数
# =======================
def tone_energy(x, freq_hz, sr):
    n = len(x)
    t = np.arange(n) / sr
    s = np.sin(2 * np.pi * freq_hz * t)
    c = np.cos(2 * np.pi * freq_hz * t)
    a = np.dot(x, s)
    b = np.dot(x, c)
    return a * a + b * b

def decode_bits_from(x, start, nbits, sr, bit_len):
    bits = []
    for i in range(nbits):
        a = start + i * bit_len
        b = a + bit_len
        if b > len(x):
            return None
        seg = x[a:b]
        seg = seg * np.hanning(len(seg))
        e0 = tone_energy(seg, F0, sr)
        e1 = tone_energy(seg, F1, sr)
        bits.append(1 if e1 > e0 else 0)
    return bits

def bits_to_int(bits):
    v = 0
    for b in bits:
        v = (v << 1) | (b & 1)
    return v

def crc8_atm(data_bytes: bytes) -> int:
    """
    CRC-8/ATM (poly=0x07, init=0x00, xorout=0x00)
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

def build_chirp_template():
    # 和 TX 一样：scipy chirp + 不加窗（TX没加窗）
    n = int(CHIRP_DUR * SR)
    t = np.arange(n) / SR
    x = chirp(t, f0=CHIRP_F0, f1=CHIRP_F1, t1=CHIRP_DUR, method="linear").astype(np.float32)
    x = x / (np.max(np.abs(x)) + 1e-9)
    return x

CHIRP_TEMPLATE = build_chirp_template()

def chirp_corr_score(x, start_idx):
    """返回从 start_idx 开始一段与 chirp 的相关强度（归一化）"""
    n = len(CHIRP_TEMPLATE)
    if start_idx < 0 or start_idx + n > len(x):
        return 0.0
    seg = x[start_idx:start_idx+n]
    seg = seg * np.hanning(len(seg))
    denom = (np.linalg.norm(seg) * np.linalg.norm(CHIRP_TEMPLATE) + 1e-12)
    return float(abs(np.dot(seg, CHIRP_TEMPLATE)) / denom)

def find_topk_chirp_peaks(x, k=3, min_gap_s=0.25):
    """在整段 x 中找 k 个最可能的 chirp 起点"""
    hop = int(HOP_S * SR)
    min_gap = int(min_gap_s * SR)

    scores = []
    for i in range(0, len(x) - len(CHIRP_TEMPLATE), hop):
        s = chirp_corr_score(x, i)
        scores.append((s, i))
    scores.sort(reverse=True, key=lambda z: z[0])

    peaks = []
    used = np.zeros(len(x), dtype=bool)
    for s, idx in scores:
        if s < CHIRP_THRESH:
            break
        left = max(0, idx - min_gap)
        right = min(len(used), idx + min_gap)
        if used[left:right].any():
            continue
        peaks.append((idx, s))
        used[left:right] = True
        if len(peaks) >= k:
            break

    peaks.sort(key=lambda z: z[0])
    return peaks

def try_decode_frame(x, chirp_start):
    """
    强化版：
    1) 在 chirp_start 附近做细搜索，找更准的 chirp 起点
    2) 在 chirp 结束后，尝试多个 bit 相位(offset)，看哪一个能 CRC 通过
    """
    chirp_len = int(CHIRP_DUR * SR)
    bit_len = int(BIT_DUR * SR)

    payload_bits = CMD_BITS + SEQ_BITS
    total_bits = payload_bits + CRC_BITS

    # -------- 1) 细化 chirp 起点（±10ms 搜索，步长2采样）--------
    search = int(0.010 * SR)   # 10ms
    best_idx = chirp_start
    best_sc = -1.0
    for off in range(-search, search + 1, 2):
        idx = chirp_start + off
        sc = chirp_corr_score(x, idx)
        if sc > best_sc:
            best_sc = sc
            best_idx = idx

    # -------- 2) 尝试多个 bit 相位（0~1bit 内 8 个相位）--------
    start0 = best_idx + chirp_len
    end0 = start0 + total_bits * bit_len
    if end0 + bit_len > len(x):
        return (False, None, None, best_sc, None, None)

    best_try = (False, None, None, best_sc, None, None)

    # 8个相位：0/8,1/8,...7/8 bit_len
    for phase in range(0, bit_len, max(1, bit_len // 8)):
        bits = decode_bits_from(x, start0 + phase, total_bits, SR, bit_len)
        if bits is None:
            continue

        data_bits = bits[:payload_bits]
        crc_bits = bits[payload_bits:]

        cmd = bits_to_int(data_bits[:CMD_BITS])
        seq = bits_to_int(data_bits[CMD_BITS:CMD_BITS+SEQ_BITS])
        rx_crc = bits_to_int(crc_bits)

        calc = crc8_atm(bytes([cmd & 0xFF, seq & 0xFF]))
        ok = (calc == rx_crc)

        # 先把每次尝试打印出来（你会看到某一次突然 ok=True）
        print(f"[frame] score={best_sc:.2f} phase={phase:3d} cmd={cmd} seq={seq} calc=0x{calc:02X} rx=0x{rx_crc:02X} ok={ok}")

        if ok:
            return (True, cmd, seq, best_sc, calc, rx_crc)

        best_try = (False, cmd, seq, best_sc, calc, rx_crc)

    return best_try

# =======================
# 主程序：实时监听
# =======================
def main():
    print("=== 第13课：实时接收机（麦克风）===")
    print(f"SR={SR}, ring={RING_S}s, hop={HOP_S}s, chirp_thresh={CHIRP_THRESH}, cooldown={COOLDOWN_S}s")
    print("现在请播放 6.tx.wav / 12B_stadium_mix_xxx.wav，或用手机播放对着麦克风。")
    print("按 Ctrl+C 结束。\n")

    ring_len = int(RING_S * SR)
    ring = np.zeros(ring_len, dtype=np.float32)

    hop = int(HOP_S * SR)
    cooldown_samples = int(COOLDOWN_S * SR)
    cooldown = 0

    last_save_t = time.time()

    stream_kwargs = dict(samplerate=SR, channels=1, dtype="float32", blocksize=hop)
    if INPUT_DEVICE is not None:
        stream_kwargs["device"] = INPUT_DEVICE

    with sd.InputStream(**stream_kwargs) as stream:
        while True:
            block, _ = stream.read(hop)      # (hop, 1)
            block = block.reshape(-1)

            # 更新 ring buffer：左移 + 追加
            ring[:-hop] = ring[hop:]
            ring[-hop:] = block

                        # ===== DEBUG：每0.5秒看一次麦克风电平 + ring里最大相关 =====
            if not hasattr(main, "_dbg_t"):
                main._dbg_t = time.time()
            if time.time() - main._dbg_t > 0.5:
                mic_level = float(np.max(np.abs(block)))
                # 在 ring 上粗扫一次最大相关（步长更大一点，避免太慢）
                step = int(0.04 * SR)  # 40ms
                best = 0.0
                for ii in range(0, len(ring) - len(CHIRP_TEMPLATE), step):
                    s = chirp_corr_score(ring, ii)
                    if s > best:
                        best = s
                print(f"[dbg] mic_level={mic_level:.4f}  max_corr={best:.3f}  thresh={CHIRP_THRESH:.3f}")
                main._dbg_t = time.time()

            if cooldown > 0:
                cooldown -= hop
                continue

            # 在 ring 上找 chirp
            peaks = find_topk_chirp_peaks(ring, k=REPEAT, min_gap_s=MIN_GAP_S)
            if len(peaks) == 0:
                continue

            # 对每个 peak 尝试解码
            got = []
            for idx, _sc in peaks:
                ok, cmd, seq, sc, calc, rx = try_decode_frame(ring, idx)
                if ok:
                    got.append((cmd, seq))

            if got:
                # 投票
                winner, cnt = Counter(got).most_common(1)[0]
                if cnt >= VOTE_MIN:
                    cmd, seq = winner
                    print(f"✅ 触发：cmd={cmd}, seq={seq}  (票数 {cnt}/{len(got)})")
                    cooldown = cooldown_samples

                    # 可选：保存触发窗口录音，便于你写报告
                    now = time.time()
                    if now - last_save_t > 1.0:
                        out = f"realtime_capture_{int(now)}.wav"
                        write(out, SR, (ring * 32767).astype(np.int16))
                        print(f"   已保存触发窗口录音：{out}")
                        last_save_t = now

            time.sleep(0.001)

if __name__ == "__main__":
    main()
```