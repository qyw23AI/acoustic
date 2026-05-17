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