我有cli.py 看得出来你的记忆已经十分混乱了，那现在你帮我干最后一件事情吧。 我在codebook.py里面写了，我需要七个指令。你教我如何生成（我要正式使用的版本），生成之后怎么测试，就这样，指令给全一点

Thought for 41s

好，这次只说你最后要用的这件事：

**用正式版 `tx.cli` 生成 7 条指令音频，以及生成后怎么测试。**

你现在正式使用的发射入口就是：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd <命令码> --seq <序号> --out <输出文件名>
```

这条命令会按你现在的正式方案生成音频，也就是：

* `chirp` 做同步
* `cmd + seq + crc`
* `2-FSK` 编码
* `repeat_n=3` 重复发送

这正是你 PDF 里最后收敛出来的主方案。

---

## 一、7 个正式指令怎么生成

你 `codebook.py` 里定义的是这 7 个命令。下面我把**命令含义 + 生成命令**一起给你。

### 1）0x8A

**武馆：R2 在端头等待，收到指令后开始拼接**

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_start_join.wav
```

### 2）0x5C

**武馆：拼接结束后判断成功，随后进行下一个端头动作**

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x5C --seq 2 --out tx_5C_next_end.wav
```

### 3）0x27

**武馆：R2 接到 R1 离开武馆指令，在 R1 离开后进入树林**

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x27 --seq 3 --out tx_27_leave_wuguan.wav
```

### 4）0xE1

**梅林：前三个梅林方块放好后，R1 完全拿走，R2 再上梅林**

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0xE1 --seq 4 --out tx_E1_enter_meilin.wav
```

### 5）0x72

**梅林：肉眼判断 R2 拿够 KFS，R1 进入对抗区后，R2 也离开梅林**

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x72 --seq 5 --out tx_72_leave_meilin.wav
```

### 6）0x39

**对抗区：R2 站到 R1 上将 KFS 放在九宫格顶层**

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x39 --seq 6 --out tx_39_place_kfs.wav
```

### 7）0x95

**全场：R2 需要重试，由 R1 给出指令**

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 7 --out tx_95_retry.wav
```

---

## 二、一次性全生成

你如果想一次把 7 条全生成，直接在仓库根目录跑这一段：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_start_join.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x5C --seq 2 --out tx_5C_next_end.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x27 --seq 3 --out tx_27_leave_wuguan.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0xE1 --seq 4 --out tx_E1_enter_meilin.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x72 --seq 5 --out tx_72_leave_meilin.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x39 --seq 6 --out tx_39_place_kfs.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 7 --out tx_95_retry.wav
```

生成后，你目录里就会有 7 个正式使用的 wav。

---

## 三、`seq` 怎么用

这个很重要。

`seq` 不是随便写着玩的，它是为了：

* 防止旧命令重放
* 防止重复触发
* 让接收端区分“这是新命令”还是“刚才那个命令又听到了一次”

所以建议你这样用：

* **同一场测试里，每发一次命令，`seq` 就加 1**
* 不要老是一直发 `seq=1`

例如：

* 第一次发开始拼接：`0x8A, seq=1`
* 第二次再发同一条开始拼接：`0x8A, seq=2`
* 再下一次：`0x8A, seq=3`

也就是说：

**`cmd` 表示“干什么”，`seq` 表示“这是第几次发这条命令”。**

---

## 四、生成之后怎么测试

你现在最应该做的是这 3 层测试。

### 1）先看 wav 能不能正常生成

生成完以后，终端应该会打印类似：

* 输出文件名
* cmd
* seq
* repeat
* duration

只要没报错，第一层就过了。

---

### 2）做离线自检

你现在已经有 `offline_decode.py`，所以最稳的自检方式是直接读自己刚生成的 wav，再解回来。

比如测 `tx_8A_start_join.wav`：

```
PYTHONPATH=$PWD/src python
```

然后输入：

```
from acoustic_comm.io.wav import read_wavfrom acoustic_comm.protocol.constants import DEFAULT_CONFIGfrom acoustic_comm.rx.offline_decode import decode_from_wavex, sr = read_wav("tx_8A_start_join.wav")out = decode_from_wave(x, DEFAULT_CONFIG)print(out)
```

理想结果是：

* `ok: True`
* `cmd: 138`（也就是 `0x8A`）
* `seq: 1`

你把文件名换掉，就能测其他 6 条。

---

### 3）做真实播放-接收测试

这是最关键的台架测试。

先开实时监听器：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.rx.realtime_listener
```

然后：

* 用手机/另一台电脑播放 `tx_8A_start_join.wav`
* 对着麦克风放
* 看终端有没有触发结果

如果正常，它应该会打印类似：

* 检测到峰
* 解出 cmd / seq
* 投票通过
* 接受触发

---

## 五、推荐测试顺序

你按这个顺序来最稳：

### 第一步

先生成一条最重要的命令，比如开始拼接：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_start_join.wav
```

### 第二步

做离线自检，确认编码解码链路没问题。

### 第三步

开 `realtime_listener.py`，做近距离播放测试。

### 第四步

再把 7 条都生成出来，逐条播，逐条验。

---

## 六、现在需不需要调参

**先不要大调。**

你现在正式使用的版本，先保持当前基线就行：

* `sr = 16000`
* `chirp_dur = 0.12`
* `chirp_f0 = 1200`
* `chirp_f1 = 3200`
* `f0 = 1500`
* `f1 = 2500`
* `bit_dur = 0.05`
* `repeat_n = 3`

这是你文档里已经验证过、并且作为当前正式基线的参数。

### 现在最值得调的不是协议参数，而是：

* 播放器真实音量
* 麦克风摆位
* 播放距离
* 如果实时监听太难触发，再小幅调 `chirp_thresh`

也就是说：

**先用默认参数跑通，再做环境调试。**

---

## 七、你现在最省事的正式用法

你以后正式生成命令音频，直接记这一条模板就够了：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd <命令码> --seq <递增序号> --out <文件名>.wav
```

比如正式比赛前，你可以准备一批文件：

* `tx_8A_start_join.wav`
* `tx_5C_next_end.wav`
* `tx_27_leave_wuguan.wav`
* `tx_E1_enter_meilin.wav`
* `tx_72_leave_meilin.wav`
* `tx_39_place_kfs.wav`
* `tx_95_retry.wav`

---

如果你要，我下一条可以直接给你一份\*\*“7 条指令的最终速查表”\*\*，你复制进 README 就能用。

你再确认一遍，现在仓库已经完整的情况下，生成音频，音频生成后，怎么测试（同一个电脑离线测试以及双设备空气通信测试），你全部都和我说

Thought for 46s

可以。我按“**现在仓库已经完整**”这个前提，给你一版**正式使用流程**。你照着做就行。

先说结论：你现在正式使用的链路就是

**`tx.cli 生成 wav` → `offline_decode 做离线闭环验证` → `realtime_listener 做空气通信测试`**。

音频结构对应你 PDF 里的主方案：**chirp 同步 + `cmd + seq + crc` + 2-FSK + 重复发送/投票**。

---

## 一、先确认你站在仓库根目录

先保证你在：

```
~/acoustic_comm
```

后面命令默认都在这个目录运行。

建议每次都带上：

```
PYTHONPATH=$PWD/src
```

这样模块导入最稳。

---

## 二、正式生成音频

你现在的正式发射入口是：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd <命令码> --seq <序号> --out <输出文件名>.wav
```

### 你这 7 个正式指令，直接这样生成

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_start_join.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x5C --seq 2 --out tx_5C_next_end.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x27 --seq 3 --out tx_27_leave_wuguan.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0xE1 --seq 4 --out tx_E1_enter_meilin.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x72 --seq 5 --out tx_72_leave_meilin.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x39 --seq 6 --out tx_39_place_kfs.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 7 --out tx_95_retry.wav
```

### 这 7 条分别对应

* `0x8A`：武馆开始拼接
* `0x5C`：拼接结束，进入下一个端头动作
* `0x27`：离开武馆
* `0xE1`：进入梅林
* `0x72`：离开梅林
* `0x39`：放 KFS
* `0x95`：重试

这些码字和用途就是你 PDF / 方案文档里那套。

### `seq` 怎么用

建议你正式测试时：

* 每发一次命令，`seq` 就加 1
* 不要一直固定 `seq=1`

因为 `seq` 的作用就是帮助接收端区分：

* 这是新命令
* 还是旧命令重复听到了

---

## 三、生成后先做最小自检

先确认底层没问题：

```
PYTHONPATH=$PWD/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -q
```

你已经跑过了，`18 passed`，这一步已经过了。

---

## 四、同一个电脑的离线测试

这个测试**不经过空气传播**，是最先该做的。

目的不是测喇叭和麦克风，而是测：

* 生成的 wav 对不对
* 解码器能不能把它自己解回来
* `cmd / seq / crc / vote` 这条链是不是通的

### 测试方法

比如你刚生成了：

```
tx_8A_start_join.wav
```

那就在仓库根目录运行：

```
PYTHONPATH=$PWD/src python - <<'PY'from acoustic_comm.io.wav import read_wavfrom acoustic_comm.protocol.constants import DEFAULT_CONFIGfrom acoustic_comm.rx.offline_decode import decode_from_wavex, sr = read_wav("tx_8A_start_join.wav")out = decode_from_wave(x, DEFAULT_CONFIG)print(out)PY
```

### 理想输出

你应该看到类似：

```
{  'ok': True,  'cmd': 138,  'seq': 1,  ...}
```

这里：

* `138` 就是十进制的 `0x8A`
* `seq` 应该等于你生成时填的那个序号

### 如何测 7 条

把文件名换掉重复跑就行，例如：

```
PYTHONPATH=$PWD/src python - <<'PY'from acoustic_comm.io.wav import read_wavfrom acoustic_comm.protocol.constants import DEFAULT_CONFIGfrom acoustic_comm.rx.offline_decode import decode_from_wavefor fn in [    "tx_8A_start_join.wav",    "tx_5C_next_end.wav",    "tx_27_leave_wuguan.wav",    "tx_E1_enter_meilin.wav",    "tx_72_leave_meilin.wav",    "tx_39_place_kfs.wav",    "tx_95_retry.wav",]:    x, sr = read_wav(fn)    out = decode_from_wave(x, DEFAULT_CONFIG)    print(fn, "->", out)PY
```

### 离线测试通过标准

7 条都应该满足：

* `ok == True`
* `cmd` 对得上
* `seq` 对得上

如果离线都过不了，就先不要做空气通信测试。

---

## 五、双设备空气通信测试

这个测试才是你真正关心的“播放设备 → 麦克风 → 实时接收”。

### 场景

* **设备 A**：发射端

可以是手机、电脑、音箱，负责播放你刚生成的 wav
* **设备 B**：接收端

运行 `realtime_listener.py` 的电脑，接麦克风

### 推荐初始条件

先不要一上来就复杂环境，先这样：

* 距离：`0.2m ~ 0.5m`
* 朝向：喇叭对着麦克风
* 环境：尽量安静
* 音量：先中等偏大，别爆音

### 第一步：接收端开实时监听

在设备 B 上运行：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.rx.realtime_listener
```

如果你的默认输入设备不是想要的麦克风，先列一下输入设备：

```
PYTHONPATH=$PWD/src python - <<'PY'from acoustic_comm.io.audio_device import print_input_devicesprint_input_devices()PY
```

如果后面你需要指定设备号，再去改 `realtime_listener.py` 里的 `device` 参数或者入口调用。

### 第二步：设备 A 播放音频

比如先播第一条：

```
tx_8A_start_join.wav
```

### 第三步：观察接收端输出

理想情况下，接收端会打印类似：

* 检测到峰
* 解码成功
* `trigger accepted: cmd=138, seq=1`

如果它能打印出正确的 `cmd` 和 `seq`，就说明空气通信跑通了。

### 第四步：7 条逐条播放

推荐顺序：

* 先播一条，确认稳定
* 再把 7 条逐条播
* 每条都用不同 `seq`

例如第二次你再测 `0x8A`，最好不要继续用 `seq=1`，而是重新生成一条：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 8 --out tx_8A_start_join_s8.wav
```

---

## 六、空气通信测试的通过标准

### 第一层：基本通过

* 接收端能识别出正确的 `cmd`
* `seq` 也正确
* 不需要多次重试

### 第二层：稳定通过

* 同一条命令连续播几次，都能识别
* 7 条都能识别
* 没有把一条命令识别成另一条

### 第三层：工程上可用

* 换一点角度、距离后仍能识别
* 有轻微背景噪声也能识别
* 没出现明显误触发

---

## 七、现在需不需要调参

### 先不要动协议主参数

你现在先保持默认基线就行：

* `sr = 16000`
* `chirp_dur = 0.12`
* `chirp_f0 = 1200`
* `chirp_f1 = 3200`
* `f0 = 1500`
* `f1 = 2500`
* `bit_dur = 0.05`
* `repeat_n = 3`

这套就是你文档里当前建议的正式基线。

### 真正先该调的是这些

先按顺序调：

#### 1\. 播放音量

原则不是越大越好，而是：

**不失真的前提下尽量大。**

太小听不出来，太大容易：

* 喇叭失真
* 麦克风削顶
* 波形变脏

#### 2\. 距离和朝向

最开始一定先近距离、正对着测。

#### 3\. 实时监听阈值

如果离线能解、空气里解不出来，再看 `realtime_listener.py` 里的：

* `chirp_thresh`

如果过高，可以小幅降低。

但这一步放在“音量、距离、设备确认都没问题之后”。

---

## 八、你现在最推荐的完整流程

### A. 生成正式音频

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_start_join.wav
```

### B. 同机离线验证

```
PYTHONPATH=$PWD/src python - <<'PY'from acoustic_comm.io.wav import read_wavfrom acoustic_comm.protocol.constants import DEFAULT_CONFIGfrom acoustic_comm.rx.offline_decode import decode_from_wavex, sr = read_wav("tx_8A_start_join.wav")print(decode_from_wave(x, DEFAULT_CONFIG))PY
```

### C. 双设备空气通信

设备 B：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.rx.realtime_listener
```

设备 A：

* 播放 `tx_8A_start_join.wav`

### D. 7 条全测

把 7 条都按上面流程测一遍。

---

## 九、如果空气通信失败，按这个顺序排查

1. **离线能不能解**

* 不能解：先修生成/解码链路
2. **麦克风设备对不对**

* 可能读错设备了
3. **音量是否太小或太大**
4. **距离是否太远**
5. **朝向是否不对**
6. **`chirp_thresh` 是否过高**
7. **环境噪声是否太大**

---

## 十、你现在最省事的一套正式命令

### 一次生成 7 条

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_start_join.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x5C --seq 2 --out tx_5C_next_end.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x27 --seq 3 --out tx_27_leave_wuguan.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0xE1 --seq 4 --out tx_E1_enter_meilin.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x72 --seq 5 --out tx_72_leave_meilin.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x39 --seq 6 --out tx_39_place_kfs.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 7 --out tx_95_retry.wav
```

### 一次离线验证 7 条

```
PYTHONPATH=$PWD/src python - <<'PY'from acoustic_comm.io.wav import read_wavfrom acoustic_comm.protocol.constants import DEFAULT_CONFIGfrom acoustic_comm.rx.offline_decode import decode_from_wavefiles = [    "tx_8A_start_join.wav",    "tx_5C_next_end.wav",    "tx_27_leave_wuguan.wav",    "tx_E1_enter_meilin.wav",    "tx_72_leave_meilin.wav",    "tx_39_place_kfs.wav",    "tx_95_retry.wav",]for fn in files:    x, sr = read_wav(fn)    out = decode_from_wave(x, DEFAULT_CONFIG)    print(fn, "=>", out)PY
```

### 开实时监听

```
PYTHONPATH=$PWD/src python -m acoustic_comm.rx.realtime_listener
```

---

如果你愿意，我下一条可以直接给你一份\*\*“比赛前测试清单”\*\*，按勾选项写，方便你现场照着验。

是不是每一条指令但凡使用第二次，seq就要变？那是不是得提前准备很多音频？

Thought for 21s

对，**如果你把 `seq` 真正用于“去重 / 防重放”**，那同一条指令第二次正式发送时，`seq` 最好要变。

但这不等于你必须提前准备成百上千个音频文件。

## 先说结论

### 在“正式接收逻辑”里

如果接收端开着 `(cmd, seq)` 去重保护，那么：

* 第一次发：`0x8A, seq=1`，会被当成新命令
* 第二次还发：`0x8A, seq=1`，**可能会被当成旧命令重放而拒绝**
* 所以第二次应该发：`0x8A, seq=2`

也就是说：

**同一条命令只要想被当成“新的有效触发”，`seq` 就应该变。**

---

## 但你不需要提前准备很多音频

你有 3 种实际做法。

### 做法 1：最推荐，现用现生成

你根本不用提前存几百个 wav。

用到哪条，就现场在终端生成一条新的：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 12 --out tx_8A_s12.wav
```

下一次再发同一条命令：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 13 --out tx_8A_s13.wav
```

这最省空间，也最灵活。

---

### 做法 2：提前给每条指令预生成一小段序号池

如果你担心现场不方便敲命令，可以提前准备，比如每条命令生成 `seq=1~10`。

例如 `0x8A` 先准备 10 条：

* `tx_8A_s01.wav`
* `tx_8A_s02.wav`
* ...
* `tx_8A_s10.wav`

7 条命令各准备 10 条，也就 **70 个文件**，其实不算多。

这在比赛前是完全可接受的。

---

### 做法 3：测试阶段先不严格管 seq

如果你现在只是台架测试、验证链路，不是正式比赛逻辑，那你可以暂时：

* 一直用同一个 `seq`
* 或者每条命令固定一个 `seq`

因为这时候你主要关心的是：

* 能不能识别
* 空气链路稳不稳
* chirp / FSK / CRC / vote 是否正常

但一旦进入“正式使用”的思路，还是建议把 `seq` 当真。

---

## 什么时候“同一音频可以重复播”

### 可以重复播的情况

* 你只是做**离线测试**
* 你只是试听音频
* 你重启了接收程序，去重状态清空了
* 你暂时没启用严格的 `(cmd, seq)` 去重策略

### 不建议重复播的情况

* 你在一次连续运行的正式接收过程中
* 接收端已经把 `(cmd, seq)` 记成“处理过”
* 你还想让它再次触发同一动作

这时就应该换新 `seq`。

---

## 你现在最实用的建议

### 如果你是“开发/台架阶段”

先这样就够：

* 7 条命令各准备 **1 条**
* 先跑通离线和空气通信

### 如果你是“正式使用/比赛前准备”

建议这样：

* 7 条命令各准备 **5~10 个不同 seq 的版本**
* 命名清楚一点，比如

* `tx_8A_s01.wav`
* `tx_8A_s02.wav`
* `tx_95_s01.wav`

这样现场就够用了。

---

## 最后一句话概括

**是的，同一条命令想第二次被当成“新命令”，`seq` 最好变。**

**但不用提前准备海量音频，现生成或者每条预生成 5~10 个版本就够。**

你要的话，我可以下一条直接给你一个**批量生成 7 条指令、每条 10 个 seq 版本**的 bash 脚本。

给我带seq的指令吧。以及假如最后在赛场上调试，你要给我什么建议吗？说过的就不用说了

Thought for 26s

可以，我直接给你两部分：

第一部分是**正式生成命令音频的带 `seq` 指令**。

第二部分是**赛场最后调试时，我额外建议你注意的点**，只说前面没展开过的。

---

## 一、带 `seq` 的正式生成指令

你现在正式入口就是：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd <命令码> --seq <序号> --out <文件名>.wav
```

### 先给你一套“每条命令一个起始 seq”的版本

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x5C --seq 1 --out tx_5C_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x27 --seq 1 --out tx_27_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0xE1 --seq 1 --out tx_E1_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x72 --seq 1 --out tx_72_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x39 --seq 1 --out tx_39_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 1 --out tx_95_s01.wav
```

对应含义：

* `0x8A`：武馆开始拼接
* `0x5C`：拼接结束，进入下一个端头动作
* `0x27`：离开武馆
* `0xE1`：进入梅林
* `0x72`：离开梅林
* `0x39`：放 KFS
* `0x95`：重试

---

## 二、如果同一条命令要用很多次

那就给同一条命令准备多个 `seq` 版本。

### 例子：`0x95` 重试命令，准备 10 个版本

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 1  --out tx_95_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 2  --out tx_95_s02.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 3  --out tx_95_s03.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 4  --out tx_95_s04.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 5  --out tx_95_s05.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 6  --out tx_95_s06.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 7  --out tx_95_s07.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 8  --out tx_95_s08.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 9  --out tx_95_s09.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x95 --seq 10 --out tx_95_s10.wav
```

### 同理，`0x8A` 也可以这样准备

```
PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 1 --out tx_8A_s01.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 2 --out tx_8A_s02.wavPYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli --cmd 0x8A --seq 3 --out tx_8A_s03.wav
```

---

## 三、最推荐的批量生成方式

你完全可以一次把 7 条命令、每条 10 个 `seq` 都生成出来。

下面这段 bash 直接在仓库根目录跑：

```
mkdir -p wav_cmdsfor cmd in 0x8A 0x5C 0x27 0xE1 0x72 0x39 0x95; do  for seq in $(seq 1 10); do    PYTHONPATH=$PWD/src python -m acoustic_comm.tx.cli \      --cmd $cmd \      --seq $seq \      --out wav_cmds/tx_${cmd}_s$(printf "%02d" $seq).wav  donedone
```

生成后目录里会有这种文件：

* `wav_cmds/tx_0x8A_s01.wav`
* `wav_cmds/tx_0x8A_s02.wav`
* ...
* `wav_cmds/tx_0x95_s10.wav`

这个办法最适合比赛前统一准备。

---

## 四、生成后怎么测

### 1）同机离线测试

生成完任意一个 wav，比如：

```
tx_0x8A_s01.wav
```

就直接跑：

```
PYTHONPATH=$PWD/src python - <<'PY'from acoustic_comm.io.wav import read_wavfrom acoustic_comm.protocol.constants import DEFAULT_CONFIGfrom acoustic_comm.rx.offline_decode import decode_from_wavex, sr = read_wav("wav_cmds/tx_0x8A_s01.wav")out = decode_from_wave(x, DEFAULT_CONFIG)print(out)PY
```

看结果里：

* `ok` 要是 `True`
* `cmd` 要对
* `seq` 要对

### 2）双设备空气通信测试

接收端电脑运行：

```
PYTHONPATH=$PWD/src python -m acoustic_comm.rx.realtime_listener
```

另一台设备播放对应 wav。

如果识别成功，终端会打印出正确的 `cmd` 和 `seq`。

---

## 五、赛场最后调试，我额外建议你做的事

你说“说过的不用说”，那我只给**新增的、偏实战操作层**的建议。

### 1\. 文件命名一定要让操作员一眼不会点错

不要只放：

* `tx_8A_s01.wav`
* `tx_5C_s01.wav`

最好带上中文动作说明，至少带缩写。比如：

* `01_8A_start_join_s01.wav`
* `02_5C_next_end_s01.wav`
* `07_95_retry_s01.wav`

原因很现实：赛场上最怕的不是算法，而是**人手点错文件**。

---

### 2\. 给操作员准备一张“seq 用过表”

非常简单，一张纸或者一个备忘录：

* 8A：用到 s03
* 5C：用到 s01
* 27：用到 s02
* 95：用到 s05

这样你不会在紧张时重复播旧 `seq`。

---

### 3\. 赛场上先固定“一条烟雾测试命令”

建议你选一条最容易观察、风险最低的命令，专门当“系统还活着吗”的快速测试命令。

通常可以选：

* `0x95` 重试
* 或者一条最容易看出 R2 有反应、但不会引发危险动作的命令

这样你每次排查时，不是 7 条都乱试，而是先用这一条判断：

* 发射链路还活着吗
* 接收链路还活着吗
* 麦克风和音箱摆位是不是还对

---

### 4\. 赛场调试时不要同时改两个东西

比如不要一边改：

* 音量
* 麦克风角度
* `chirp_thresh`

然后一次全试。

不然你根本不知道到底是哪一个起作用。

赛场上最稳的方式是：

* 一次只动一个旋钮
* 每次只用一条固定测试命令
* 成功/失败立刻记

---

### 5\. 实际比赛前，把“播放链路”锁死

一旦你用某个设备、某个播放器、某个音量档位调通了，**比赛前不要临时换播放软件/系统音效路径**。

比如不要临时从：

* VLC 换成浏览器
* 手机外放换成蓝牙
* 系统均衡器突然打开
* 某个播放器自动开“音效增强”

这种变化很容易把波形整脏。

---

### 6\. 优先验证“电机开着时”的效果

真正危险的是：静态测试都好，机器人一开电机就全变了。

所以最后阶段一定要测这几种状态：

* R2 静止
* R2 电机空转
* R1/R2 同时工作
* 麦克风放在最终安装位

你最终信的，只能是**这个状态下的结果**，不是桌面静态结果。

---

### 7\. 不要只测“能不能识别”，要测“会不会认错”

最后阶段最容易忽视的是：

* 播 8A，结果识别成 95
* 播 27，结果识别成 39

所以最后调试要做一个最简单的“混淆检查”：

* 7 条各播几次
* 记录每次识别出的 `cmd`
* 看有没有串码

只看“有反应”是不够的，得看“反应是不是对的”。

---

### 8\. 给自己留一个“最后兜底版本”

建议你把一套“保守可用版本”单独存一份，不要赛场上直接覆盖。

比如：

* `stable_cmds/`
* 里面放你最终确认过的 7 条 wav

这样你赛场临时调出来的新版本如果反而更差，还能立刻退回稳定版本。

---

### 9\. 最后一分钟只做链路确认，不做协议重构

如果到赛场上还有问题，最后优先改的是：

* 文件选取
* `seq` 是否重复
* 播放音量
* 摆位
* 麦克风设备
* `chirp_thresh`

不要到最后一刻再去改：

* `f0/f1`
* `bit_dur`
* `chirp_dur`
* `repeat_n`

这种已经属于“重构协议”，代价太大。

---

## 六、我建议你比赛前实际准备成这样

### 目录结构建议

```
wav_cmds/  01_8A_start_join_s01.wav  01_8A_start_join_s02.wav  ...  07_95_retry_s10.wav
```

### 现场操作建议

* 每条命令准备 `5~10` 个 `seq`
* 每播一次就往后用下一个 `seq`
* 准备一张纸记哪个命令用到哪个 `seq`
* 再单独留一套 `stable_cmds/` 兜底

---

如果你要，我下一条可以直接给你一份\*\*“7 条命令 × 每条 10 个 seq”的最终批量生成脚本\*\*，我把文件名按比赛可操作的方式全写好。