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
