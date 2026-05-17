# acoustic_comm

用于机器人项目中 **R1 → R2 的辅助声学编码通信模块**。

主通信方式为 AprilTag 识别，声学通信作为辅助链路使用，负责在视觉链路不稳定、需要快速触发、或需要关键兜底时下发少量离散命令。

本仓库提供：

- 固定命令到音频的编码
- chirp 同步 + 2-FSK 调制
- wav 生成
- 离线解码
- 实时监听
- 噪声 / 频偏 / 混响评估脚本
- 辅助测试与分析工具

---

## 1. 设计目标

1. 为 R1 与 R2 提供一条独立于视觉链路的辅助通信通道
2. 在保证基本可靠性的前提下，尽量缩短 wav 时长，提高机器人实时反应速度
3. 对不同性质的动作使用不同链路：
   - **Fast**：低时延，适合流程推进类动作
   - **Slow**：更稳健，适合关键动作、重试、停止等命令
4. 降低现场操作复杂度，不要求操作手记忆十六进制命令或维护序号

---

## 2. 命令表

仓库内部仍然使用固定 `CMD_ID`，但对人操作时建议直接使用命令别名。

| Alias | CMD_ID | 链路 | 含义 |
|---|---:|---|---|
| `start_splice` | `0x8A` | Fast | 武馆：R2 在端头等待，收到指令后开始拼接 |
| `next_terminal` | `0x5C` | Slow | 武馆：拼接结束后判断成功，随后进行下一个端头动作 |
| `enter_merlin` | `0x27` | Fast | 武馆：R2 接到 R1 离开武馆指令，在 R1 离开后进入梅林 |
| `climb_merlin` | `0xE1` | Fast | 梅林：前三个梅林方块放好后，R1 完全拿走，R2 再上梅林 |
| `leave_merlin` | `0x72` | Fast | 梅林：R2 拿够 KFS，R1 进入对抗区后，R2 也离开梅林 |
| `place_on_top` | `0x39` | Slow | 对抗区：R2 站到 R1 上，将 KFS 放在九宫格顶层 |
| `retry` | `0x95` | Slow | 全场：R2 需要重试 |
| `stop` | `0xC6` | Slow | 全场：STOP / ABORT，立刻停下当前由声学触发的动作 |

---

## 3. 码字选取原则

CMD_ID 需要具有识别性。选取原则如下：

1. 任意两条指令的 8bit 编码，最好至少有 3 位以上不同
2. 编码尽量 0/1 均衡
3. 编码尽量有翻转，降低受噪声与频偏影响时的误判风险

### 码字池

| 推荐序号 | CMD_ID | 二进制 | 说明 |
|:---:|:---:|---|---|
| 1 | `0x8A` | `10001010` | 基础核心码字（均衡、翻转多） |
| 2 | `0x5C` | `01011100` | 与 #1 汉明距 = 5（≥5） |
| 3 | `0x27` | `00100111` | 与 #1 = 5、与 #2 = 6（前三条两两 ≥ 5） |
| 4 | `0xE1` | `11100001` | 加入后前 4 条两两 ≥ 4 仍成立 |
| 5 | `0x72` | `01110010` | 加入后前 5 条两两 ≥ 4 仍成立 |
| 6 | `0x39` | `00111001` | 加入后前 6 条两两 ≥ 4 仍成立 |
| 7 | `0x95` | `10010101` | 加入后前 7 条两两 ≥ 4 仍成立 |
| 8 | `0xC6` | `11000110` | 从这里起降为“全局 ≥ 3” |
| 9 | `0x4B` | `01001011` | 0/1 很均衡、翻转多；整体区分度较好 |
| 10 | `0xCD` | `11001101` | 区分度不错 |
| 11 | `0x57` | `01010111` | 均衡、翻转多 |
| 12 | `0xA4` | `10100100` | 均衡、结构清晰 |
| 13 | `0x68` | `01101000` | 均衡、与部分码字差异较大 |
| 14 | `0xB3` | `10110011` | 1 的数量略多 |
| 15 | `0xD0` | `11010000` | 1 的数量略少 |

---

## 4. 协议概览

### Fast 链路

用于对时延敏感的流程推进类动作。

- Payload：`cmd`
- 重复次数：`2`
- 校验：无 CRC
- 目标：低时延

### Slow 链路

用于关键动作、安全动作、重试等命令。

- Payload：`cmd + crc`
- 重复次数：`2`
- 校验：CRC-8
- 目标：更稳健

### 操作原则

- 对人暴露的是 **动作名**
- 对代码内部保留的是 **固定 CMD_ID**
- 不要求操作手维护序号

---

## 5. 音频参数

### 通用参数

- `sr = 16000`
- `f0 = 1500 Hz`
- `f1 = 2500 Hz`
- `bit_dur = 0.05 s`
- `fade_ms = 8.0`

### Fast 链路参数

- `chirp_dur = 0.06`
- `chirp_f0 = 1200`
- `chirp_f1 = 3200`
- `cmd_bits = 8`
- `seq_bits = 0`
- `crc_bits = 0`
- `silence_head_s = 0.01`
- `silence_tail_s = 0.00`
- `gap_s = 0.02`
- `repeat_n = 2`

### Slow 链路参数

- `chirp_dur = 0.08`
- `chirp_f0 = 1200`
- `chirp_f1 = 3200`
- `cmd_bits = 8`
- `seq_bits = 0`
- `crc_bits = 8`
- `silence_head_s = 0.02`
- `silence_tail_s = 0.00`
- `gap_s = 0.06`
- `repeat_n = 2`

---

## 6. 波形结构

### Fast

```text
[silence_head] + [chirp] + [cmd]
gap
[silence_head] + [chirp] + [cmd]
```

时长：

* 单帧：`0.01 + 0.06 + 8 * 0.05 = 0.47 s`
* 总长：`0.47 + 0.02 + 0.47 = 0.96 s`

### Slow

```
[silence_head] + [chirp] + [cmd + crc]gap[silence_head] + [chirp] + [cmd + crc]
```

时长：

* 单帧：`0.02 + 0.08 + 16 * 0.05 = 0.90 s`
* 总长：`0.90 + 0.06 + 0.90 = 1.86 s`

---

## 7\. 同步与判决

### chirp 同步

本仓库使用 chirp 作为同步头。

* Fast 使用上扫频：`1200 -> 3200`
* Slow 使用上扫频：`1200 -> 3200`

虽然 Fast 与 Slow 的 chirp 方向相同，但两者在 chirp 时长、payload 长度、CRC 配置和整体帧结构上不同，因此实时监听器仍可在单进程中同时尝试 fast / slow 两套解码路径，再选择匹配更好的结果。

### payload 解码

1. 检测 chirp 峰值
2. 根据 chirp 起点定位 payload
3. 逐 bit 解码
4. 对 Slow 链路执行 CRC 校验
5. 输出候选帧并做命令合法性检查

---

## 8\. 静音与 fade

波形结构采用：

```
[silence_head] + [chirp] + [payload]
```

并保留帧间 `gap`。

### 规则

1. 保留 `silence_head`，给 chirp 提供干净起点
2. 不使用 `silence_tail`
3. 保留 `gap` 以分隔重复帧，避免粘连
4. chirp 和 FSK payload 都使用 fade，减少 click / pop 和边界宽频能量

---

## 9\. 仓库结构

### 核心代码目录

```
src/acoustic_comm
├── dsp
│   ├── chirp_sync.py
│   ├── fsk.py
│   ├── resample_shift.py
│   └── tone.py
├── eval
│   ├── drift_clock.py
│   ├── false_alarm.py
│   ├── snr_sweep_pink_reverb.py
│   ├── snr_sweep_white.py
│   └── stadium_mix.py
├── io
│   ├── audio_device.py
│   └── wav.py
├── protocol
│   ├── codebook.py
│   ├── constants.py
│   ├── crc.py
│   └── frame.py
├── rx
│   ├── offline_decode.py
│   ├── postprocess.py
│   └── realtime_listener_working.py
└── tx
    ├── build_waveform.py
    └── cli.py
```

### 根目录辅助工具与资源

```
configs/
generated_wavs/
markdown/
recordings/
scripts/
tests/
tmp/
tools/
```

### tools

```
tools
├── analyze_fast_recording.py
├── check_chirp_direction.py
├── gen_fast_carrier_sweep.py
└── record_wav.py
```

### 目录职责

* `protocol/`：命令表、参数、帧格式、CRC
* `dsp/`：chirp、FSK、tone、频偏处理
* `tx/`：发射端 wav 构建与命令行接口
* `rx/`：离线解码、实时监听、状态化峰值扫描与触发控制
* `io/`：音频设备与 wav 读写
* `eval/`：噪声、混响、频偏等评估脚本
* `tools/`：录音、chirp 方向检查、fast 载频扫描、录音分析等辅助测试工具
* `scripts/`：历史实验脚本与兼容性测试脚本
* `tests/`：基础单元测试
* `generated_wavs/`：生成好的示例音频
* `recordings/`：现场录音与回灌分析文件
* `tmp/`：临时扫描与分析产物

---

## 10\. 安装

推荐使用 conda：

```
conda env create -f environment.ymlconda activate acoustic_comm
```

运行命令时，建议在仓库根目录带上：

```
PYTHONPATH=src
```

---

## 11\. 生成音频

推荐直接使用**动作别名**，不要求记十六进制。

### 生成 Fast 命令

```
PYTHONPATH=src python -m acoustic_comm.tx.cli --name start_splicePYTHONPATH=src python -m acoustic_comm.tx.cli --name enter_merlinPYTHONPATH=src python -m acoustic_comm.tx.cli --name climb_merlinPYTHONPATH=src python -m acoustic_comm.tx.cli --name leave_merlin
```

默认输出文件名类似：

* `fast_start_splice.wav`
* `fast_enter_merlin.wav`
* `fast_climb_merlin.wav`
* `fast_leave_merlin.wav`

### 生成 Slow 命令

```
PYTHONPATH=src python -m acoustic_comm.tx.cli --name next_terminalPYTHONPATH=src python -m acoustic_comm.tx.cli --name place_on_topPYTHONPATH=src python -m acoustic_comm.tx.cli --name retryPYTHONPATH=src python -m acoustic_comm.tx.cli --name stop
```

默认输出文件名类似：

* `slow_next_terminal.wav`
* `slow_place_on_top.wav`
* `slow_retry.wav`
* `slow_stop.wav`

### 自定义输出路径

```
PYTHONPATH=src python -m acoustic_comm.tx.cli --name stop --out stop_button.wav
```

---

## 12\. 离线自测

建议先做纯软件自测，再上设备。

### Fast 自测

```
PYTHONPATH=src python - <<'PY'from acoustic_comm.protocol.constants import FAST_CONFIGfrom acoustic_comm.tx.build_waveform import build_tx_wavefrom acoustic_comm.rx.offline_decode import decode_from_wavex = build_tx_wave(0x8A, cfg=FAST_CONFIG)res = decode_from_wave(x, cfg=FAST_CONFIG)print("wave_len_s =", len(x) / FAST_CONFIG.sr)print(res)PY
```

### Slow 自测

```
PYTHONPATH=src python - <<'PY'from acoustic_comm.protocol.constants import SLOW_CONFIGfrom acoustic_comm.tx.build_waveform import build_tx_wavefrom acoustic_comm.rx.offline_decode import decode_from_wavex = build_tx_wave(0x39, cfg=SLOW_CONFIG)res = decode_from_wave(x, cfg=SLOW_CONFIG)print("wave_len_s =", len(x) / SLOW_CONFIG.sr)print(res)PY
```

### STOP 自测

```
PYTHONPATH=src python - <<'PY'from acoustic_comm.protocol.constants import SLOW_CONFIGfrom acoustic_comm.tx.build_waveform import build_tx_wavefrom acoustic_comm.rx.offline_decode import decode_from_wavex = build_tx_wave(0xC6, cfg=SLOW_CONFIG)res = decode_from_wave(x, cfg=SLOW_CONFIG)print("wave_len_s =", len(x) / SLOW_CONFIG.sr)print(res)PY
```

---

## 13\. 实时监听

实时监听器使用**单进程双路径、状态化扫描**方案：

* 内部同时建立 fast chirp 模板和 slow chirp 模板
* 同时尝试 fast / slow 两套解码路径
* 只处理新的 chirp 峰值，避免重复扫描旧峰
* Fast 与普通 Slow 当前允许单帧有效即接受
* STOP 默认要求更强确认（两帧有效）

### 启动监听

```
PYTHONPATH=src python -m acoustic_comm.rx.realtime_listener
```

启动后会常驻运行，直到 `Ctrl+C` 停止。

### 当前实时监听策略说明

* Fast 侧额外使用预期重复窗口做配对，减少错误重复峰带来的误触发
* Listener 启动时包含短暂 warmup，用于避开设备初始化瞬态
* 调试输出中会提示输入峰值与潜在 clipping 情况

---

## 14\. 触发保护与运行策略

当前实时监听器采用以下策略抑制误触发与重复触发：

* **post-accept holdoff**：一次触发被接受后，在一段时间内忽略后续输入尾波
* **clear ring after accept**：触发后清空 ring buffer，避免尾音再次参与解码
* **stateful peak scan**：只处理新的 chirp 峰值，不重复扫描历史峰
* **score floor（Fast）**：Fast 链路对过低分数候选不接受，降低误触发概率

默认配置下：

* Fast holdoff：约 `1.25 s`
* 普通 Slow holdoff：约 `2.0 s`
* STOP holdoff：约 `3.0 s`

---

## 15\. 噪声、频偏与实测建议

### 已知结论

* 白噪声下，SNR 降到约 `-15 dB` 后性能开始下降
* 粉噪声结果与白噪声相近
* 频率偏移 / 采样率偏差会明显影响检测成功率
* 接收端必须保留一定测量容差

### 实测建议

* 测试不同距离下的成功率
* 测试电机噪声影响
* 测试场地混响
* 测试喇叭 / 麦克风频响
* 测试不同音量下的漏检率和误检率
* 普通 Slow 可先独立验收
* `stop` 建议最终单独做专项验收，重点看最坏场景下的可靠性与响应速度

---

## 16\. 硬件建议

* 使用定向喇叭 / 定向麦克风
* 或者喇叭加简单号角 / 导音管
* 麦克风加短声管
* 减少机器人自身电机噪声直灌麦克风
* 降低空气传播带来的随机性

---

## 17\. 辅助工具

### 1）录音工具

```
PYTHONPATH=src python tools/record_wav.py --out recordings/test.wav --dur 4
```

用于录制现场输入，便于回灌分析。

### 2）chirp 方向检查

```
PYTHONPATH=src python tools/check_chirp_direction.py \  --wav slow_next_terminal.wav \  --head-s 0.02 \  --chirp-s 0.08
```

用于验证生成 wav 中 chirp 的实际方向。

### 3）Fast 载频扫描

```
PYTHONPATH=src python tools/gen_fast_carrier_sweep.py
```

用于批量生成不同载频组合下的 Fast 命令音频，做对比实验。

### 4）Fast 录音分析

```
PYTHONPATH=src python tools/analyze_fast_recording.py \  --wav recordings/fast_start_splice_f0_1500_f1_2500_recorded.wav \  --expect start_splice \  --f0 1500 --f1 2500
```

用于分析录音中每个 bit 在两路载频上的能量表现，辅助定位频响不均衡、切窗偏移等问题。

---

## 18\. 项目总结

本仓库提供一套面向机器人辅助通信的声学编码方案：

* 命令使用固定 8 bit `CMD_ID`
* 命令按用途分为 Fast / Slow 两类
* Fast 负责低时延
* Slow 负责关键动作与安全动作
* `stop` 作为 Slow 链路中的安全命令保留，建议最终单独做可靠性验收
* 操作手使用动作别名，不需要记忆十六进制
* 实时监听器使用单进程双路径自动识别快慢链路
* 声学链路与主视觉链路配合使用，共同提升比赛中的鲁棒性与可控性