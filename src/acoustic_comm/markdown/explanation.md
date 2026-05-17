# 一、这套仓库现在到底在做什么

你现在这套正式代码，核心目标其实就一句话：

**把一个命令 `cmd + seq (+ crc)` 编成声学波形发出去，再从麦克风录到的音频里把它解回来。**

而且走的是你 PDF 里的主方案：

* 用 **chirp** 做同步起点检测
* 用 **2-FSK** 表示 bit
* 帧里放 `cmd + seq + crc`
* 同一帧 **重复发送**
* 接收端做 **CRC 校验 + 多数投票**

这就是你现在仓库的主线。

---

# 二、各目录和文件在做什么

## 1）`protocol/`

这是**协议层**，决定“发什么”和“怎么解释”。

### `constants.py`

全局参数中心。

定义了：

* 采样率 `sr=16000`
* chirp 参数
* FSK 两个频率 `f0=1500, f1=2500`
* `bit_dur=0.05`
* 帧结构长度
* 重复发送次数 `repeat_n=3`
* 帧前后静音、帧间 gap
* fade 长度

你以后大部分“系统级参数”都是从这里看。

### `crc.py`

CRC-8/ATM 校验。

作用是：

* 发送时算 CRC
* 接收时验证 frame 有没有错

### `frame.py`

负责：

* `cmd, seq` 打包成 frame
* frame 转 bit / bit 转 frame
* 检查 frame CRC 是否正确

也就是协议字节层。

### `codebook.py`

命令码表。

把 `0x8A / 0x5C / 0x27 ...` 这些命令码映射成中文含义，主要给人看、给日志看。

---

## 2）`dsp/`

这是**数字信号处理层**，决定“声音怎么生成”和“怎么从声音里测出 bit”。

### `tone.py`

最底层音频片段生成：

* `tone()`：生成单频正弦
* `silence()`：生成静音
* `apply_fade()`：淡入淡出

### `fsk.py`

2-FSK 的核心：

* `fsk_encode_bits()`：把 bit 串编码成 FSK 音频
* `tone_energy()`：测某个频率的能量
* `decide_bit()`：比较 `f0/f1` 哪个强
* `decode_bits_from()`：从某个起点开始解 bit

### `chirp_sync.py`

同步层：

* `make_chirp()`：生成 chirp
* `make_chirp_template()`：生成用于匹配的模板
* `find_chirp_peak()`：找单个最佳 chirp 峰
* `find_topk_chirp_peaks()`：找多个峰，用于重复帧

### `resample_shift.py`

评测用的扰动模拟：

* `time_stretch_linear()`：模拟采样率偏差/时钟偏差
* `freq_shift_multiply()`：模拟频偏

这个主要给 `eval/` 用。

---

## 3）`tx/`

这是**发射端**。

### `build_waveform.py`

真正生成完整发射波形的地方。

它干的事情是：

1. `pack_frame(cmd, seq, cfg)` 得到 `cmd + seq + crc`
2. `bytes_to_bits()` 转成 bit 串
3. 前面加一个 chirp
4. payload 用 2-FSK 编成音频
5. 再加前后静音
6. 按 `repeat_n` 重复几次
7. 拼成完整 tx waveform

也就是说，**你最后要的 tx.wav，本质就是这里做出来的**。

### `cli.py`

命令行入口。

这是你最常用的一个发射入口。

---

## 4）`rx/`

这是**接收端**。

### `offline_decode.py`

离线解码器。

输入是一整段 wav，输出解码结果：

* 找 chirp
* 找 payload 起点
* 解 bit
* 转 frame
* CRC 校验
* 投票

适合先在电脑台架验证。

### `postprocess.py`

后处理：

* 多数投票
* 冷却时间
* `(cmd, seq)` 去重防重复触发

### `realtime_listener.py`

实时监听器。

直接从麦克风读音频，实时找 chirp、解码、投票、输出触发结果。

这个是以后接近现场使用状态的入口。

---

## 5）`io/`

音频输入输出。

### `wav.py`

读写 wav 文件。

### `audio_device.py`

麦克风设备枚举、录音、打开实时输入流。

---

## 6）`eval/`

评测层，专门做“这套方案在噪声/混响/频偏下表现怎么样”。

### `snr_sweep_white.py`

白噪声 SNR 扫描。

### `snr_sweep_pink_reverb.py`

粉噪 + 混响 扫描。

### `drift_clock.py`

频偏 + 时钟偏差 压测。

### `false_alarm.py`

纯噪声下测误触发。

### `stadium_mix.py`

把 tx.wav 混进现场背景噪声里，生成更像比赛环境的测试音频。

---

## 7）`tests/`

单元测试：

* `test_crc.py`
* `test_frame_roundtrip.py`
* `test_fsk_basic.py`

先保证底层逻辑没坏。

---

# 三、怎么生成你需要的音频

你 PDF 里的主方案，不是最开始那个简单 beep，也不是 preamble-only，而是：

**`[silence] + [chirp] + [payload(cmd+seq+crc 的 FSK)] + [silence]`，并重复发送多次。**

你现在对应的正式入口，就是：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx.wav
```

这个会生成一条 `tx.wav`。

比如：

* `0x8A`：武馆开始拼接
* `seq=1`：序号 1

如果你想生成别的命令：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x5C --seq 2 --out tx_5c.wav
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x27 --seq 3 --out tx_27.wav
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 4 --out tx_retry.wav
```

如果你想临时改重复次数：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --repeat 3 --out tx.wav
```

你现在的默认配置已经是：

* `sr=16000`
* `chirp_dur=0.12`
* `f0=1500`
* `f1=2500`
* `bit_dur=0.05`
* `repeat_n=3`

这和你 PDF 主线是对得上的。

---

# 四、怎么解码这个音频

## 离线解码

你现在有 `offline_decode.py`，它本质上是库函数，不是现成 CLI。

所以目前最方便的是后面我再帮你补一个 `rx/cli.py`，或者你先在 Python 里这样试：

```
from acoustic_comm.io.wav import read_wavfrom acoustic_comm.protocol.constants import DEFAULT_CONFIGfrom acoustic_comm.rx.offline_decode import decode_from_wavex, sr = read_wav("tx.wav")out = decode_from_wave(x, DEFAULT_CONFIG)print(out)
```

## 实时监听

实时监听器入口是：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.rx.realtime_listener
```

然后你用手机/音箱播放 `tx.wav`，它就会尝试从麦克风里解出来。

---

# 五、现在需不需要调参

## 先说结论

**现在先不要大调。**

先用默认参数跑通，再看实测结果决定。

## 你当前最不应该乱动的

这些先保持 PDF 基线：

* `sr = 16000`
* `chirp_dur = 0.12`
* `chirp_f0 = 1200`
* `chirp_f1 = 3200`
* `f0 = 1500`
* `f1 = 2500`
* `bit_dur = 0.05`
* `repeat_n = 3`

这些是你的“主方案骨架”，不是一开始就该到处拧的旋钮。

## 现在最值得调的，其实是这几类

### 1\. 现场播放音量

不是代码里的 `amp` 一直加大，而是：

* 先保持 `amp=0.35`
* 现场用播放器/音箱音量去调

原则是：

**在不失真的前提下尽量大。**

### 2\. 实时监听阈值

以后最可能调的是这些运行时参数：

* `chirp_thresh`
* `vote_min`
* `cooldown_s`

这几个对“能不能稳、会不会误触发”影响很大。

### 3\. `fade_ms`

这个一般不用大动，`5~10 ms` 都合理。

你现在 `8 ms` 挺合适。

---

# 六、你现在推荐怎么用这套东西

我建议你按这个顺序走。

## 第一步：先跑测试

```
PYTHONPATH=$PWD/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -q
```

## 第二步：先生成一条标准发射音频

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx.wav
```

## 第三步：播放这条音频，做台架验证

* 手机/电脑播放 `tx.wav`
* 另一台设备麦克风收音
* 先近距离测

## 第四步：用实时监听器试

```
PYTHONPATH=$PWD/src python -m acoustic_comm.rx.realtime_listener
```

## 第五步：再做评测

比如白噪扫描：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.eval.snr_sweep_white --cmd 0x8A --seq 1
```

粉噪 + 混响：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.eval.snr_sweep_pink_reverb --cmd 0x8A --seq 1
```

频偏/时钟偏差：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.eval.drift_clock --cmd 0x8A --seq 1
```

误触发：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.eval.false_alarm
```

---

# 七、你现在最可能遇到的坑

第一，`pytest` 外部插件干扰。

已经解决方案了：

```
PYTHONPATH=$PWD/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -q
```

第二，VS Code 黄线不代表真报错。

优先看终端能不能 import。

第三，实时监听器最容易卡在：

* 麦克风设备不对
* 播放器音量太小
* `chirp_thresh` 过高
* 距离太远或环境太吵