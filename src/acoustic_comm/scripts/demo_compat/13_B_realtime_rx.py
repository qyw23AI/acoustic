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