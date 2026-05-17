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