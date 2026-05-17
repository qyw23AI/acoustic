从这段 log 看，问题**不像是 fast 门槛太高**，而是监听器当前**根本没有形成 fast 候选**。你现在这版 `main()` 里已经把 fast 放得很宽了：`fast_chirp_thresh=0.03`、`fast_accept_min=1`、`fast_accept_score_min=0.0`。按这套配置，只要抓到一个能解出来的 fast 帧，理论上就会触发。

还有一个很关键的点：你看到的 `fast_score=0.0000`**不是“chirp 匹配分真的为 0”**，而是代码里写的是：

* `fast_candidate is None` → 就直接显示 `fast_score=0.0`
* `slow_candidate is None` → 就直接显示 `slow_score=0.0`

也就是说，这个 debug 目前只能说明“没有候选”，**不能区分**是“完全没看到 chirp 峰”，还是“看到了 chirp，但后面的 frame decode/check 失败”。

我建议你按这个顺序查，最快。

### 1）先固定输入设备，不要用默认 `device=None`

你现在启动时没有打印 `input_device=...`，说明走的是默认输入设备。Linux 下这一步很容易踩坑：程序在听笔记本内置麦，你实际对着 USB 麦 / 监听声卡在播。`listen_forever()` 支持传 `device`，但 `main()` 里现在传的是 `None`。

先列设备：

```
python - <<'PY'import sounddevice as sdprint(sd.query_devices())PY
```

然后直接指定设备跑，不要走 `main()`：

```
PYTHONPATH=src python - <<'PY'from acoustic_comm.rx.realtime_listener import listen_forever, RealtimeListenerConfigfrom acoustic_comm.protocol.constants import FAST_CONFIG, SLOW_CONFIGrt_cfg = RealtimeListenerConfig(    fast_accept_min=1,    slow_accept_min=1,    stop_accept_min=2,    clear_ring_after_accept=True,    fast_post_accept_s=1.25,    slow_post_accept_s=2.0,    stop_post_accept_s=3.0,    fast_chirp_thresh=0.03,    slow_chirp_thresh=0.10,    fast_repeat_tol_s=0.05,    clip_warn_level=0.90,    fast_accept_score_min=0.0,    startup_warmup_s=1.5,    verbose_debug=True,    save_debug_ring=True,    debug_ring_path="debug_ring.wav",)listen_forever(    fast_cfg=FAST_CONFIG,    slow_cfg=SLOW_CONFIG,    rt_cfg=rt_cfg,    device=你的设备号,    on_trigger=None,)PY
```

### 2）先做“纯软件自测”，确认 fast 编解码链本身没坏

README 里已经给了 fast 自测方式。这个测试**不经过麦克风/喇叭**，如果这一步都不通，就是协议或代码问题；如果这一步通，问题就在真实音频链路。

```
PYTHONPATH=src python - <<'PY'from acoustic_comm.protocol.constants import FAST_CONFIGfrom acoustic_comm.tx.build_waveform import build_tx_wavefrom acoustic_comm.rx.offline_decode import decode_from_wavex = build_tx_wave(0x8A, cfg=FAST_CONFIG)res = decode_from_wave(x, cfg=FAST_CONFIG)print("wave_len_s =", len(x) / FAST_CONFIG.sr)print(res)PY
```

这一步如果能正确解出来，说明：

* fast 的 `chirp_dur / f0 / f1 / bit_dur`
* fast 的 frame 结构
* realtime 之外的 decode 逻辑

基本都没问题。README 里 fast 参数就是 `chirp 1200->3200, dur=0.06s`，总长约 `0.96s`。

### 3）录一段真实播放，再用仓库自带工具分析

README 里已经有两个很适合你现在场景的工具：录音工具 `record_wav.py`，还有 `analyze_fast_recording.py`。这一步能直接判断是：

* 根本没录到 fast chirp
* 录到了 chirp，但 bit 能量不对
* 频响把 `1500/2500` 某一路吃掉了
* 切窗偏移 / 时序偏了

先录：

```
PYTHONPATH=src python tools/record_wav.py --out recordings/fast_test.wav --dur 4
```

一边录一边播放你的 fast wav。然后分析：

```
PYTHONPATH=src python tools/analyze_fast_recording.py \  --wav recordings/fast_test.wav \  --expect start_splice \  --f0 1500 --f1 2500
```

这两个工具在 README 里都已经列出来了。

### 4）把 realtime 的 debug 改成“看原始 chirp 峰”，现在的信息还不够

你现在的 debug 只能看到“有没有 candidate”，看不到 `find_topk_chirp_peaks()` 的结果。我建议你在 `_collect_mode_candidate()` 里临时加一段：

```
    peaks = find_topk_chirp_peaks(        x=wave,        chirp_tpl=chirp_tpl,        sr=cfg.sr,        k=rt_cfg.search_topk,        min_gap_s=rt_cfg.min_gap_s,        score_threshold=_chirp_thresh_for_mode(mode, rt_cfg),        use_abs=True,    )    if rt_cfg.verbose_debug:        top = ", ".join(f"({int(p)}, {float(s):.4f})" for p, s in peaks[:5])        print(f"[{mode}] peaks={len(peaks)} top=[{top}]")
```

再在 `_decode_frame_near_peak()` 返回后，加一段：

```
        if rt_cfg.verbose_debug:            print(                f"[{mode}] abs_peak={abs_peak} ok={item['ok']} "                f"cmd={item['cmd']} seq={item['seq']} "                f"score={item['score']:.4f} phase={item['phase']}"            )
```

这样你马上就能分清：

* `peaks=0`：没看到 chirp，同步阶段就挂了
* `peaks>0` 但 `ok=False`：看到 chirp 了，但 payload decode / frame check 失败
* `ok=True` 但没触发：再看 mode/cmd 匹配或候选选择逻辑

你当前代码的 debug 之所以看不出来，就是因为它只打印 candidate 级别的 `fast_score/slow_score`。

### 我对你这个现象的优先判断

如果 **slow 能听到、fast 听不到**，那我首怀疑的是这几个方向：

1. **输入设备选错了**
2. **真实链路把 60ms fast chirp 搞坏了**，而 80ms slow chirp 更稳
3. **喇叭 / 麦克风 / 系统降噪 / AGC** 把 fast 的起始 chirp 和 bit 边界抹掉了
4. **你播出来的 wav 不是 FAST\_CONFIG 生成的那个文件**
5. **录到了声音，但没录到有效频段**，比如 1200→3200 chirp 或 1500/2500 FSK 被频响压得太厉害

README 里 fast 本来就是“低时延链路”，chirp 更短、总帧也更短；现场一旦混响、AGC、扬声器频响不理想，slow 通而 fast 不通是很常见的现象。

### 先别急着继续降阈值

你现在 fast 阈值已经到 `0.03` 了，而且 `fast_accept_score_min=0.0`。再盲目降阈值，收益通常不大，误触发风险会先上来。更值钱的是先搞清楚到底卡在：

* chirp 检测前
* chirp 检测后、bit 解码前
* bit 解码后、frame check 前

你把 `recordings/fast_test.wav` 的分析结果，或者加完上面那两段 debug 后的新日志贴上来，我可以直接帮你判断是哪一层坏了。

你这个列表里，**外接麦克风大概率就是 `0`**：

```
0 Usb Audio Device: USB Audio (hw:1,0), ALSA (1 in, 0 out)
```

判断依据很直接：

* 名字就是 `Usb Audio Device`
* `(1 in, 0 out)` 表示它是**1 路输入、0 路输出**
* 很像一个纯 USB 麦克风

反而 `7 default` 只是系统默认设备，不一定真指到你这个外接麦。

所以你现在先直接用 **`device=0`** 测。

你这份监听器代码本身支持传 `device`，传了以后还会打印 `input_device=...`。

最直接的做法是，把 `realtime_listener.py` 里 `main()` 末尾这段：

```
listen_forever(    fast_cfg=FAST_CONFIG,    slow_cfg=SLOW_CONFIG,    rt_cfg=rt_cfg,    device=None,    on_trigger=None,)
```

改成：

```
listen_forever(    fast_cfg=FAST_CONFIG,    slow_cfg=SLOW_CONFIG,    rt_cfg=rt_cfg,    device=0,    on_trigger=None,)
```

然后再跑：

```
PYTHONPATH=src python -m acoustic_comm.rx.realtime_listener
```

启动后如果看到：

```
input_device=0
```

就说明已经明确在用这个 USB 麦克风了。

你也可以先单独验证一下 0 号设备能不能打开：

```
python - <<'PY'import sounddevice as sdprint(sd.query_devices(0))sd.check_input_settings(device=0, samplerate=16000, channels=1, dtype='float32')print("device 0 input OK")PY
```

如果这条通过，说明：

* 设备号对
* 16 kHz / 单声道输入也没问题

那监听器就应该优先用它。

顺手说一下你这几个设备里最值得关注的只有两个：

* `0` = 真实 USB 麦克风，优先选它
* `7` = 系统默认，不稳定，不建议排查时使用

所以现在就先一句话：**把监听器里的 `device=None` 改成 `device=0`。**

你改完再贴一段新日志，我可以继续帮你看 fast 为什么还没起来。

这行报错的意思很明确：

```
PortAudioError: Invalid sample rate [PaErrorCode -9997]
```

就是 **0 号这个 USB 麦克风不能直接用 16000 Hz 打开**。

你选到的设备没错，它就是外接麦；错的是 **采样率不被这个设备当前驱动路径支持**。

你贴出来的设备信息里也有个信号：

```
'default_samplerate': 44100.0
```

说明这个设备默认更像是跑 **44.1k**，不一定支持 **16k** 直开。

而你的监听器这边是**强制按 16000 Hz 开流**的：

* `FAST_CONFIG` 和 `SLOW_CONFIG` 要求同一个 `sr`
* README 也写了通用参数 `sr = 16000`
* `listen_forever()` 里会拿这个 `sr` 去 `open_input_stream(...)`。

所以现在的本质是：

**USB 麦本身可用，但它的 `hw:1,0` 这条路径不接受 16k。**

你先这样排。

### 先测这个麦到底支持哪些采样率

跑这个：

```
python - <<'PY'import sounddevice as sdrates = [8000, 16000, 22050, 32000, 44100, 48000]for r in rates:    try:        sd.check_input_settings(device=0, samplerate=r, channels=1, dtype='float32')        print(r, "OK")    except Exception as e:        print(r, "FAIL:", e)PY
```

这一步会直接告诉你 0 号设备能不能开 16k、44.1k、48k。

### 大概率可行的办法 1：不要用 `0`，改用 `1` 或 `7`

因为：

* `0 = hw:1,0`，更像**硬件直通**
* `1 = sysdefault`
* `7 = default`

后两者通常更可能带 **ALSA 的软件转换 / 重采样**，有时 16k 可以过。

你先测：

```
python - <<'PY'import sounddevice as sdfor dev in [1, 7]:    try:        sd.check_input_settings(device=dev, samplerate=16000, channels=1, dtype='float32')        print("device", dev, "16k OK")    except Exception as e:        print("device", dev, "16k FAIL:", e)PY
```

如果 `1` 或 `7` 里有一个 `16k OK`，那监听器就直接用那个设备号。

### 大概率可行的办法 2：麦克风只能 44.1k / 48k，那就代码里做重采样

如果你测出来是：

* 16000 不行
* 44100 或 48000 可以

那说明硬件采集没问题，只是**协议要求的 16k**和**设备原生采样率**不一致。

这时候要么：

* 用 `default/sysdefault` 让系统帮你转到 16k
* 要么在 `open_input_stream` / `listen_forever` 里先按 44100 或 48000 采，再软件重采样到 16000 后送解码

因为你这套协议参数是按 `sr=16000` 设计的，不能直接把协议里的 `sr` 改成 44100 就完事，不然 chirp 长度、bit 长度、解码时序都会一起变。

### 你现在最该做的

先不要改协议，也不要继续猜设备号。就按这两步走：

1. 先跑“支持采样率探测脚本”
2. 再跑“device 1 / 7 的 16k 检查”

你很可能会得到这种结果之一：

* `device 0: 16000 FAIL, 44100 OK, 48000 OK`
* `device 1` 或 `7`: `16000 OK`

如果是第二种，就直接把监听器改成那个设备号。

如果全都 `16000 FAIL`，我下一步就直接帮你把实时监听改成“44.1k/48k 采集 + 实时重采样到 16k”的版本。

对，这下已经定位清楚了。

**不是 fast 检不到的第一问题了。**

现在的首要问题是：

* 你的机器人麦克风设备 `0` 只能开 **44100 / 48000**
* 但当前监听器是**硬按 16000 Hz 开输入流**
* 所以程序在“采集入口”就已经不成立了，后面的 fast/slow 检测都还没真正开始。`listen_forever()` 现在就是把 `fast_cfg.sr` 直接传给 `open_input_stream(sr=sr, ...)`，而这套协议参数本身也是按 `sr=16000` 设计的。

你既然说机器人上就固定用这个设备，那正确做法不是换设备，而是：

**用设备 0 以 48000 采集，再实时重采样到 16000 后送进现有解码器。**

我建议直接用 **48000**，因为它到 16000 是**整 3:1**，比 44100 更顺手。

---

## 你直接这样改

先改 `src/acoustic_comm/rx/realtime_listener.py`。

### 1）补 import

把文件开头 imports 改成这样：

```
from __future__ import annotationsimport mathimport timefrom dataclasses import dataclassfrom pathlib import Pathfrom typing import Callableimport numpy as npfrom scipy.signal import resample_poly
```

---

### 2）给 `RealtimeListenerConfig` 加一个输入采样率

在 dataclass 里加这一行：

```
input_sr: int | None = None
```

放在 `startup_warmup_s` 后面就行，例如：

```
    fast_accept_score_min: float = 0.20    startup_warmup_s: float = 0.5    input_sr: int | None = None
```

---

### 3）加一个重采样 helper

放到 `_update_ring()` 前后都可以：

```
def _resample_block(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:    x = np.asarray(x, dtype=np.float32)    if len(x) == 0 or src_sr == dst_sr:        return x    g = math.gcd(int(src_sr), int(dst_sr))    up = int(dst_sr // g)    down = int(src_sr // g)    y = resample_poly(x, up=up, down=down)    return np.asarray(y, dtype=np.float32)
```

---

### 4）改 `listen_forever()` 里的采集逻辑

把函数开头这一段：

```
    sr = fast_cfg.sr    hop = max(1, int(round(rt_cfg.hop_s * sr)))    ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))    ring = np.zeros(ring_len, dtype=np.float32)
```

改成：

```
    sr = fast_cfg.sr                   # 协议/解码采样率，仍然固定 16000    input_sr = sr if rt_cfg.input_sr is None else int(rt_cfg.input_sr)    hop = max(1, int(round(rt_cfg.hop_s * sr)))           # 解码域 hop（16k）    hop_in = max(1, int(round(rt_cfg.hop_s * input_sr)))  # 采集域 hop（48k）    ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))    ring = np.zeros(ring_len, dtype=np.float32)
```

然后把打印配置那段：

```
    print(        f"sr={sr}, hop={rt_cfg.hop_s}s, ring={rt_cfg.ring_s}s, "
```

改成：

```
    print(        f"sr={sr}, input_sr={input_sr}, hop={rt_cfg.hop_s}s, ring={rt_cfg.ring_s}s, "
```

---

### 5）把打开输入流和读 block 的部分改掉

把这一段：

```
        with open_input_stream(            sr=sr,            blocksize=hop,            device=device,            dtype="float32",            channels=1,        ) as stream:            while True:                block, _overflowed = stream.read(hop)                block = np.asarray(block, dtype=np.float32).reshape(-1)                _update_ring(ring, block)                sample_clock += len(block)
```

改成：

```
        with open_input_stream(            sr=input_sr,            blocksize=hop_in,            device=device,            dtype="float32",            channels=1,        ) as stream:            while True:                raw_block, _overflowed = stream.read(hop_in)                raw_block = np.asarray(raw_block, dtype=np.float32).reshape(-1)                mic_level = float(np.max(np.abs(raw_block))) if len(raw_block) else 0.0                block = _resample_block(raw_block, src_sr=input_sr, dst_sr=sr)                # 保证 block 长度稳定在解码域 hop                if len(block) > hop:                    block = block[:hop]                elif len(block) < hop:                    block = np.pad(block, (0, hop - len(block)))                _update_ring(ring, block)                sample_clock += len(block)
```

---

### 6）把 debug 里的 `mic_level` 改成复用上面的值

你文件里现在有几处这种：

```
mic_level = float(np.max(np.abs(block))) if len(block) else 0.0
```

把它们删掉，直接用前面已经算好的 `mic_level`。

也就是这两处：

* suppress 分支里的 debug
* 正常分支里的 debug

都不要重新从 `block` 算了，直接打印已有的 `mic_level`。

这样你看到的是**原始麦克风输入幅度**，更合理。当前 debug 代码就在这些位置。

---

### 7）把 `main()` 改成设备 0 + 输入 48k

把最后的 `main()` 改成这样：

```
def main() -> None:    rt_cfg = RealtimeListenerConfig(        fast_accept_min=1,        slow_accept_min=1,        stop_accept_min=2,        clear_ring_after_accept=True,        fast_post_accept_s=1.25,        slow_post_accept_s=2.0,        stop_post_accept_s=3.0,        fast_chirp_thresh=0.03,        slow_chirp_thresh=0.10,        fast_repeat_tol_s=0.05,        clip_warn_level=0.90,        fast_accept_score_min=0.0,        startup_warmup_s=1.5,        input_sr=48000,    )    listen_forever(        fast_cfg=FAST_CONFIG,        slow_cfg=SLOW_CONFIG,        rt_cfg=rt_cfg,        device=0,        on_trigger=None,    )
```

---

## 改完后你应该看到什么

启动后应当类似：

```
=== Realtime acoustic listener (stateful) ===sr=16000, input_sr=48000, hop=0.02s, ring=3.0s, ...input_device=0
```

这才说明链路是：

**机器人麦克风 48k 采集 → 实时重采样到 16k → 按现有协议解码**

---

## 为什么这是正路

因为你的协议参数和实时监听器的模板、bit 长度、chirp 长度，全都围绕 `sr=16000` 在跑；仓库说明里通用参数也是 `sr = 16000`。所以不能简单把整套协议 sr 改成 48000，那会把 chirp/payload 时长对应的样本数全部改掉。

你现在这个设备 0 已经证明：

* `16000` 不支持
* `48000` 支持

所以“48k 采集 + 16k 解码”就是最稳的机器人方案。

把这版改完再跑一次，把新启动日志和一小段 `[dbg]` 输出贴给我。

你这次贴的仓库结构和 `constants.py` 很关键，现在可以说得更准了：

**结论：先不要改音频。**

你现在遇到的这个问题，**不是发射 wav 的问题**，而是**接收端麦克风输入流打不开 16k** 的问题。

你的 `constants.py` 里，`sr` 不是一个“随便存的参数”，它直接参与了这些核心时序：

```
bit_len   = round(sr * bit_dur)chirp_len = round(sr * chirp_dur)fade_len  = round(sr * fade_ms / 1000)
```

也就是说：

* `FAST_CONFIG.sr = 16000`
* `SLOW_CONFIG.sr = 16000`

这不仅决定了生成出来的 wav 采样率，也决定了**接收端模板长度、bit 长度、chirp 长度、帧定位方式**。你 README 里通用参数也是 `sr = 16000`。

所以这件事要分开看。

## 1）你现在这个报错，改音频没用

你已经验证了设备 0：

* `16000 FAIL`
* `44100 OK`
* `48000 OK`

这说明 **robot 上这个 USB 麦硬件输入只支持 44.1k / 48k**。

而当前实时监听器是按协议里的 `sr=16000` 去开输入流的。

所以当前卡住的是：

**“麦克风怎么采进来”**

不是：

**“你生成的 fast/slow wav 对不对”**

换句话说，哪怕你把 `generated_wavs/*.wav` 全部重生一遍，只要 listener 还在拿设备 0 直开 16k，这个入口问题还是在。

---

## 2）你现有的 wav，原则上不用改

在你当前架构里：

* `cli` 负责生成音频
* `constants.py` 定义协议参数
* `realtime_listener` 负责听

那只要你还想保持这套协议是 **16k 协议**，你现在这些音频：

* `generated_wavs/fast_*.wav`
* `generated_wavs/slow_*.wav`

**都先不用动。**

因为现在的矛盾不是“发出去的波形协议不对”，而是“接收硬件不能按 16k 采集”。

---

## 3）只有在一种情况下，你才需要改音频

只有你决定做**协议级迁移**时，才需要改音频：

### 把整套协议从 16k 改成 48k

那就不是只改 `cli` 了，而是要一起改：

* `FAST_CONFIG.sr`
* `SLOW_CONFIG.sr`
* 所有基于 `bit_len / chirp_len / fade_len` 的发送和接收逻辑
* 重新生成所有 wav
* 重新验收阈值、窗口、peak 搜索、fast repeat offset
* 重新做实录测试

因为一旦 `sr` 从 16000 改成 48000：

* `chirp_len` 变 3 倍
* `bit_len` 变 3 倍
* payload 的样本长度全变
* realtime 的 chirp 模板也全变

这已经不是“换个采样率”了，而是**整套协议样本时序重定义**。

所以如果你只是想让 robot 上这个设备 0 能正常听，**最小正确改法不是改音频，而是改接收入口。**

---

## 4）所以你现在其实只有两个方向

### 方向 A：协议继续保持 16k

这是我更建议的。

那就：

* **音频不用改**
* `constants.py` 不用改
* `generated_wavs` 不用改
* 改的是 **listener / 输入层**

让它按 48k 采麦，再转成 16k 送给现有解码

这属于“适配硬件输入”。

### 方向 B：整套协议升到 48k

这是大改。

那就：

* 要改 `constants.py`
* 要重生 wav
* 要改 listener 模板和时序
* 要重新调参数

这属于“重定义协议”。

---

## 5）你现在先别动 `generated_wavs`

你这一步最稳的判断就是：

**不要为了这个设备 0 的采样率问题去改 tx 音频。**

因为这不会解决当前报错。

你现在如果坚持“先不改 `realtime_listener`”，那也至少要接受一个事实：

**当前这版 listener 在设备 0 上，不能直接工作。**

因为设备 0 已经明确不支持 16k 输入。

---

## 6）我对你仓库的具体建议

按你这套分层，最合理的是：

* `constants.py` 继续保持现在这样，协议还是 16k
* `cli` 和 `generated_wavs` 先完全不动
* 真正动的地方应该是：

* `io/audio_device.py`
* 或 `rx/realtime_listener.py`

也就是把“采集采样率”和“协议采样率”分开。

你要是愿意，我下一条就按你这个仓库结构，**只基于你现有文件职责**，给你一个最小改动方案：

* `constants.py` 不动
* `cli` 不动
* `generated_wavs` 不动
* 只改 `audio_device.py + realtime_listener.py`

让设备 0 用 48000 采进来，再喂给 16000 的现有 fast/slow 解码链。

我现在看明白你的仓库分工了，你说得对：

* `cli` 负责生成音频
* `constants.py` 负责协议参数
* `realtime_listener` 只负责听
* `audio_device.py` 只是 `sounddevice` 的一层薄包装

所以先给你一个明确结论：

**你的音频先不用改。**

原因很直接。你贴的 `audio_device.open_input_stream()` 只是原样调用：

```
return sd.InputStream(    samplerate=sr,    blocksize=blocksize,    channels=channels,    dtype=dtype,    device=device,)
```

它**没有任何重采样**。而 `realtime_listener.listen_forever()` 里又是直接拿 `fast_cfg.sr` 当输入流采样率去开设备；你现在 `main()` 里还固定了 `device=0`。所以对你这个机器人麦来说，当前问题是：

**设备 0 不能按 16000 采集，程序在“开麦”这一步就卡住了。**

这和你发射出去的 wav 对不对，是两回事。`realtime_listener.py` 当前就是这么走的。

### 所以要不要改音频

分两种情况。

**情况 1：你想保留现有协议不变。**

那就：

* `constants.py` 不改
* `cli` 不改
* `generated_wavs/*.wav` 不改

只需要处理**接收端设备采样率不匹配**。

这也是我建议的做法。

**情况 2：你想把整套协议改成 48000。**

那才需要改音频，而且不只是改音频，还得一起改：

* `FAST_CONFIG.sr`
* `SLOW_CONFIG.sr`
* chirp 模板长度
* bit 长度
* 各种窗口、阈值、repeat offset
* 然后重新生成 wav，重新验收

这属于重做协议，不是你现在最该动的地方。

### 结合你这两个文件，最小正确改法是什么

按你现在这套仓库，**`audio_device.py` 可以不动**。

真正需要最小改动的是 `realtime_listener.py`：

* 麦克风按 `48000` 采
* 采进来以后重采样到 `16000`
* 后面整套 fast/slow 解码逻辑保持原样

因为你的协议仍然是 16k 协议，ring、chirp 模板、bit 长度这些都应该继续在 16k 域里工作。`listen_forever()` 现在也是把 `sr = fast_cfg.sr` 当成整条链的时基。

### 你现在最适合的判断

你刚才说“我先不改 realtime\_listener”，这我理解。

但基于你贴出来的两个文件，现在可以非常明确地说：

**如果不改 listener，又坚持用 device 0，那它就是没法正常工作的。**

因为：

* `audio_device.py` 不会帮你转采样率
* `realtime_listener.py` 会拿 `sr=16000` 直接去开 `device=0`
* 而你已经验证过 `device=0` 对 `16000` 是 `Invalid sample rate`

这不是推测，是你当前代码路径决定的。

### 我建议你现在这样做

先保持这些都不动：

* `constants.py`
* `cli.py`
* `generated_wavs/`
* `tmp/fast_carrier_sweep/`

只改 `realtime_listener.py`，而且只做一件事：

**增加一个“输入采样率 input\_sr”和“读完后重采样到协议 sr”的入口适配。**

你这个仓库里，这才是最小且对架构最干净的改法。

我可以下一条直接按你这份 `realtime_listener.py`，给你一个**只改几处的最小 diff**，不碰 `constants.py`，不碰 `cli`，不碰发射音频。

可以。按你这个仓库分层，**只改 `src/acoustic_comm/rx/realtime_listener.py`** 就够了：

* `audio_device.py` 不改
* `constants.py` 不改
* `cli.py` 不改
* `generated_wavs/*.wav` 不改

因为你当前协议本来就是 `sr=16000`，实时监听也是按这套 fast/slow 双路径在解码；问题只在于当前 listener 直接拿协议采样率去开麦，而你的 `device=0` 只支持 `44100/48000`，不支持 `16000`。

下面就是**所有改动点**。

---

## 1）改 imports

把文件开头这段：

```
from __future__ import annotationsimport timefrom dataclasses import dataclassfrom pathlib import Pathfrom typing import Callableimport numpy as np
```

改成：

```
from __future__ import annotationsimport mathimport timefrom dataclasses import dataclassfrom pathlib import Pathfrom typing import Callableimport numpy as npfrom scipy.signal import resample_poly
```

---

## 2）给 `RealtimeListenerConfig` 增加输入采样率

你当前 `RealtimeListenerConfig` 里最后是：

```
    fast_accept_score_min: float = 0.20    startup_warmup_s: float = 0.5
```

改成：

```
    fast_accept_score_min: float = 0.20    startup_warmup_s: float = 0.5    # microphone/device capture rate; protocol/decode still uses cfg.sr    input_sr: int | None = None
```

你当前配置类就是这块结构。

---

## 3）新增一个重采样 helper

在 `_update_ring()` 前面或后面，加这个函数：

```
def _resample_block(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:    """    Resample one input block from device sample rate to protocol sample rate.    """    x = np.asarray(x, dtype=np.float32)    if len(x) == 0 or src_sr == dst_sr:        return x    g = math.gcd(int(src_sr), int(dst_sr))    up = int(dst_sr // g)    down = int(src_sr // g)    y = resample_poly(x, up=up, down=down)    return np.asarray(y, dtype=np.float32)
```

---

## 4）改 `listen_forever()` 开头的采样率/块长计算

你当前这里是：

```
    sr = fast_cfg.sr    hop = max(1, int(round(rt_cfg.hop_s * sr)))    ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))    ring = np.zeros(ring_len, dtype=np.float32)
```

改成：

```
    sr = fast_cfg.sr    input_sr = sr if rt_cfg.input_sr is None else int(rt_cfg.input_sr)    # decode/protocol domain    hop = max(1, int(round(rt_cfg.hop_s * sr)))    ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))    ring = np.zeros(ring_len, dtype=np.float32)    # device/capture domain    hop_in = max(1, int(round(rt_cfg.hop_s * input_sr)))
```

你当前 listener 确实是直接 `sr = fast_cfg.sr`，然后拿这个 `sr` 去开输入流。

---

## 5）改启动打印，把 `input_sr` 打出来

你当前打印是：

```
    print(        f"sr={sr}, hop={rt_cfg.hop_s}s, ring={rt_cfg.ring_s}s, "
```

改成：

```
    print(        f"sr={sr}, input_sr={input_sr}, hop={rt_cfg.hop_s}s, ring={rt_cfg.ring_s}s, "
```

这样启动时你能明确看到：

* 协议解码采样率 `sr=16000`
* 设备采集采样率 `input_sr=48000`

---

## 6）改 `warmup_until_samples`

你当前是：

```
    warmup_until_samples = int(round(rt_cfg.startup_warmup_s * sr))
```

这个保持在**解码域**是对的，所以仍然写成：

```
    warmup_until_samples = int(round(rt_cfg.startup_warmup_s * sr))
```

这行不用改，只是我说明一下：`sample_clock` 后面会继续按**重采样后的 16k 域**累计，所以 warmup 逻辑还能保持一致。

---

## 7）把打开输入流和读 block 的部分改掉

你当前这段是关键问题点：

```
        with open_input_stream(            sr=sr,            blocksize=hop,            device=device,            dtype="float32",            channels=1,        ) as stream:            while True:                block, _overflowed = stream.read(hop)                block = np.asarray(block, dtype=np.float32).reshape(-1)                _update_ring(ring, block)                sample_clock += len(block)
```

改成下面这整段：

```
        with open_input_stream(            sr=input_sr,            blocksize=hop_in,            device=device,            dtype="float32",            channels=1,        ) as stream:            while True:                raw_block, _overflowed = stream.read(hop_in)                raw_block = np.asarray(raw_block, dtype=np.float32).reshape(-1)                mic_level = float(np.max(np.abs(raw_block))) if len(raw_block) else 0.0                block = _resample_block(raw_block, src_sr=input_sr, dst_sr=sr)                # keep decode-domain block length stable                if len(block) > hop:                    block = block[:hop]                elif len(block) < hop:                    block = np.pad(block, (0, hop - len(block)))                _update_ring(ring, block)                sample_clock += len(block)                ring_start_abs = int(sample_clock - len(ring))
```

这一步改完后，listener 就变成：

* 麦克风按 `input_sr=48000` 采
* 每个 `raw_block` 重采样成 `16000`
* 后面的 ring、chirp 模板、bit decode、fast/slow 逻辑全部继续用原来的 16k 协议域

这正好符合你 README 里“协议参数是 16k，实时监听是 fast/slow 双路径”的现有设计。

---

## 8）debug 里的 `mic_level` 不要再从 `block` 重新算

你当前有两处会重新算：

### suppress 分支里这段

原来：

```
                        mic_level = float(np.max(np.abs(block))) if len(block) else 0.0                        remain = max(0.0, suppress_until - now_mono)                        clip_tag = " CLIP!" if mic_level >= rt_cfg.clip_warn_level else ""
```

改成：

```
                        remain = max(0.0, suppress_until - now_mono)                        clip_tag = " CLIP!" if mic_level >= rt_cfg.clip_warn_level else ""
```

### 正常 debug 分支里这段

原来：

```
                    mic_level = float(np.max(np.abs(block))) if len(block) else 0.0                    fast_ready = fast_candidate is not None
```

改成：

```
                    fast_ready = fast_candidate is not None
```

也就是说：

* `mic_level` 只在读到 `raw_block` 时算一次
* 后面 debug 直接复用

这样打印出来的 `mic=` 是**原始麦克风输入幅度**，更符合你想排机器人现场输入的目的。你当前 debug 打印逻辑就在这两个位置。

---

## 9）改 `main()`，显式指定 `input_sr=48000`

你当前 `main()` 里已经把 `device=0` 固定了。

把：

```
def main() -> None:    rt_cfg = RealtimeListenerConfig(        fast_accept_min=1,        slow_accept_min=1,        stop_accept_min=2,        clear_ring_after_accept=True,        fast_post_accept_s=1.25,        slow_post_accept_s=2.0,        stop_post_accept_s=3.0,        fast_chirp_thresh=0.03,        slow_chirp_thresh=0.10,        fast_repeat_tol_s=0.05,        clip_warn_level=0.90,        fast_accept_score_min=0.0,        startup_warmup_s=1.5,    )    listen_forever(        fast_cfg=FAST_CONFIG,        slow_cfg=SLOW_CONFIG,        rt_cfg=rt_cfg,        device=0,        on_trigger=None,    )
```

改成：

```
def main() -> None:    rt_cfg = RealtimeListenerConfig(        fast_accept_min=1,        slow_accept_min=1,        stop_accept_min=2,        clear_ring_after_accept=True,        fast_post_accept_s=1.25,        slow_post_accept_s=2.0,        stop_post_accept_s=3.0,        fast_chirp_thresh=0.03,        slow_chirp_thresh=0.10,        fast_repeat_tol_s=0.05,        clip_warn_level=0.90,        fast_accept_score_min=0.0,        startup_warmup_s=1.5,        input_sr=48000,    )    listen_forever(        fast_cfg=FAST_CONFIG,        slow_cfg=SLOW_CONFIG,        rt_cfg=rt_cfg,        device=0,        on_trigger=None,    )
```

## 11）改完后怎么跑

```
PYTHONPATH=src python -m acoustic_comm.rx.realtime_listener
```

你启动后应该看到类似：

```
=== Realtime acoustic listener (stateful) ===sr=16000, input_sr=48000, hop=0.02s, ring=3.0s, ...input_device=0
```

只要看到这个，就说明：

* 协议仍然是 16k
* 机器人麦设备 0 按 48k 采进来了
* listener 已经开始在 16k 域里做 fast/slow 解码

你把改完后的启动日志贴给我，我继续帮你看 fast 检测。

你说得对。

我收回“主要就是采样率”的判断。

现在这条链路已经能以 `input_sr=48000` 打开设备 0 了，但**打开设备成功 ≠ 检测一定正常**。而且我上一个改法里，确实有一个很可能把你原来能检出的系统改坏的点：

**我把 48k→16k 的重采样做成了“每个 20ms block 单独重采样，再裁剪/补零”。**

这会在 block 边界引入不连续，短 chirp 和 FSK bit 很容易被抹坏。你的实时监听本来就是围绕 `sr=16000` 的时序、模板、stateful peak scan 在工作的，这种分块无状态重采样很可能直接让候选变成 `none`。

所以现在正确结论是：

* **音频不用改**
* `constants.py` 不用改
* `cli.py` 不用改
* 还是改 `realtime_listener.py`
* 但不是“每块重采样”，而是**维护一个 48k 的原始 ring，再把整个 ring 重采样到 16k 去解码**

这更符合你现在 listener 的结构。

---

## 你现在要改的地方

只改 `src/acoustic_comm/rx/realtime_listener.py`。

### 1）保留这些 import

文件开头应该有：

```
import mathfrom scipy.signal import resample_poly
```

这个不用撤。

---

### 2）`RealtimeListenerConfig` 里的 `input_sr` 也保留

这个也不用撤：

```
input_sr: int | None = None
```

---

### 3）`_resample_block()` 这个 helper 也保留

这个函数可以继续用：

```
def _resample_block(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:    """    Resample one input block from device sample rate to protocol sample rate.    """    x = np.asarray(x, dtype=np.float32)    if len(x) == 0 or src_sr == dst_sr:        return x    g = math.gcd(int(src_sr), int(dst_sr))    up = int(dst_sr // g)    down = int(src_sr // g)    y = resample_poly(x, up=up, down=down)    return np.asarray(y, dtype=np.float32)
```

名字虽然叫 block，但后面我们拿它去重采样整个 raw ring。

---

## 4）把 `listen_forever()` 开头这段替换掉

你现在大概是这样：

```
sr = fast_cfg.srinput_sr = sr if rt_cfg.input_sr is None else int(rt_cfg.input_sr)# decode/protocol domainhop = max(1, int(round(rt_cfg.hop_s * sr)))ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))ring = np.zeros(ring_len, dtype=np.float32)# device/capture domainhop_in = max(1, int(round(rt_cfg.hop_s * input_sr)))
```

改成：

```
sr = fast_cfg.srinput_sr = sr if rt_cfg.input_sr is None else int(rt_cfg.input_sr)# decode/protocol domain (16k)hop = max(1, int(round(rt_cfg.hop_s * sr)))ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))ring = np.zeros(ring_len, dtype=np.float32)# device/capture domain (48k for your USB mic)hop_in = max(1, int(round(rt_cfg.hop_s * input_sr)))raw_ring_len = max(hop_in, int(round(rt_cfg.ring_s * input_sr)))raw_ring = np.zeros(raw_ring_len, dtype=np.float32)
```

核心新增的是：

* `raw_ring_len`
* `raw_ring`

---

## 5）把 while 循环里“每块重采样”的部分替换掉

你现在大概是这样：

```
raw_block, _overflowed = stream.read(hop_in)raw_block = np.asarray(raw_block, dtype=np.float32).reshape(-1)mic_level = float(np.max(np.abs(raw_block))) if len(raw_block) else 0.0block = _resample_block(raw_block, src_sr=input_sr, dst_sr=sr)if len(block) > hop:    block = block[:hop]elif len(block) < hop:    block = np.pad(block, (0, hop - len(block)))_update_ring(ring, block)sample_clock += len(block)ring_start_abs = int(sample_clock - len(ring))
```

把这整段改成：

```
raw_block, _overflowed = stream.read(hop_in)raw_block = np.asarray(raw_block, dtype=np.float32).reshape(-1)mic_level = float(np.max(np.abs(raw_block))) if len(raw_block) else 0.0# 先维护 48k 原始 ring_update_ring(raw_ring, raw_block)# 每轮把整个 raw ring 重采样到 16k 解码域ring = _resample_block(raw_ring, src_sr=input_sr, dst_sr=sr)# 保持 decode ring 长度固定，且保留“最新”的那一段if len(ring) > ring_len:    ring = ring[-ring_len:]elif len(ring) < ring_len:    ring = np.pad(ring, (ring_len - len(ring), 0))# sample_clock 继续按解码域的时间前进，不再按单块重采样结果长度累计sample_clock += hopring_start_abs = int(sample_clock - len(ring))
```

这里最关键的变化有两个：

第一，**不再对每个 20ms 小块单独重采样**。

第二，`sample_clock` 改成固定 `+= hop`，保持你的 stateful peak scan 还在 16k 域里稳定前进。

---

## 6）其他地方不用动

下面这些都保持不变：

* `fast_tpl / slow_tpl`
* `_collect_mode_candidate(...)`
* `_decode_frame_near_peak(...)`
* `_choose_best_candidate(...)`
* `main()` 里的 `input_sr=48000`
* `device=0`

因为协议域还是 16k，chirp 模板和 bit 解码都应该继续在 16k 上做。

---

## 7）我建议你再顺手加一个“peak debug”

因为你现在的 `[dbg]` 只能看到：

* `fast_candidate is None`
* `slow_candidate is None`

看不到到底是：

* 根本没 peak
* 还是有 peak，但 decode 失败

在 `_collect_mode_candidate()` 里，`peaks = find_topk_chirp_peaks(...)` 后面，加这段：

```
    if rt_cfg.verbose_debug:        top = ", ".join(f"({int(p)}, {float(s):.4f})" for p, s in peaks[:5])        print(f"[{mode}] peaks={len(peaks)} top=[{top}]")
```

然后在 `main()` 里把：

```
verbose_debug=False,
```

改成：

```
verbose_debug=True,
```

这样你下一次跑的时候，就能直接看到：

* `peaks=0`
* 或者 `peaks>0` 但后续没候选

这个信息很值钱。

---

## 8）你现在不用改音频

再强调一遍：

* `generated_wavs/*.wav` 不用改
* `FAST_CONFIG` / `SLOW_CONFIG` 不用改
* `cli.py` 不用改

因为你以前“能把所有指令检测到”，这恰恰说明你的**协议和发射 wav 本身大概率没坏**。

现在更像是：

1. 先有一个“设备 0 不能直开 16k”的入口问题
2. 然后我给你的第一版“分块重采样”又把实时检测质量搞坏了

所以这一步应该修 listener 的输入适配，而不是去动音频。

---

## 9）你改完后怎么看结果

重新跑：

```
PYTHONPATH=src python -m acoustic_comm.rx.realtime_listener
```

然后拿一个你以前确定能检出的命令，先从 **slow** 开始测，再测 fast。

你贴给我两样东西就够了：

* 启动后的前几行
* 出现播放时那一段新的 debug，包括 `[fast] peaks=...` / `[slow] peaks=...`

这样我就能继续判断是：

* chirp 同步没起来
* 还是 chirp 有了，但 bit 解码没起来。

下面是**整份改过的 `src/acoustic_comm/rx/realtime_listener.py`**。

这版只改监听入口，协议参数、`constants.py`、`cli`、生成音频都不动；核心变化是：

* 用 `device=0` 按 `input_sr=48000` 采集
* 维护一个 **48k 原始 raw\_ring**
* 每轮把整个 `raw_ring` 重采样到 **16k 协议域** 再做原来的 fast/slow 解码
* `clear_ring_after_accept` 时同时清空 `ring` 和 `raw_ring`

你当前原文件确实是直接拿 `sr=fast_cfg.sr` 去开输入流，所以这一步是针对你设备 0 只支持 `44100/48000` 的适配。

```python
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.signal import resample_poly

from ..dsp.chirp_sync import find_topk_chirp_peaks, make_chirp_template
from ..dsp.fsk import decode_bits_from
from ..io.audio_device import open_input_stream
from ..io.wav import write_wav
from ..protocol.codebook import cmd_name, is_fast_cmd, is_slow_cmd
from ..protocol.constants import AcousticConfig, FAST_CONFIG, SLOW_CONFIG
from ..protocol.frame import bits_to_bytes, check_frame


STOP_CMD = 0xC6


@dataclass(frozen=True)
class RealtimeListenerConfig:
    """
    Runtime-only parameters for realtime listening.
    New policy:
    - Fast / ordinary Slow: one valid frame is enough
    - STOP: require two valid frames
    - after accept: clear ring and suppress for a short window
    """
    hop_s: float = 0.02
    ring_s: float = 3.0
    min_gap_s: float = 0.20
    search_topk: int = 8

    # separate thresholds for fast / slow chirp search
    fast_chirp_thresh: float = 0.10
    slow_chirp_thresh: float = 0.10

    # accept policy
    fast_accept_min: int = 1
    slow_accept_min: int = 1
    stop_accept_min: int = 2

    # refine chirp locally around coarse peak
    refine_window_s: float = 0.01
    refine_step_samples: int = 2

    # try several bit-phase offsets after chirp
    phase_div: int = 8

    # debug / capture
    debug_every_s: float = 0.5
    verbose_debug: bool = False
    save_debug_ring: bool = False
    debug_ring_path: str = "debug_ring.wav"

    # accepted-trigger capture
    save_capture: bool = False
    capture_dir: str = "."
    capture_prefix: str = "realtime_capture"

    # post-accept behavior
    clear_ring_after_accept: bool = True
    fast_post_accept_s: float = 1.25
    slow_post_accept_s: float = 2.0
    stop_post_accept_s: float = 3.0

    # fast packet structure prior: 2 repeats, second chirp should appear
    # around first_abs_peak + expected_repeat_offset_samples(cfg)
    fast_repeat_tol_s: float = 0.05

    # debug aid for clipping
    clip_warn_level: float = 0.90

    fast_accept_score_min: float = 0.20

    startup_warmup_s: float = 0.5

    # microphone/device capture rate; protocol/decode still uses cfg.sr
    input_sr: int | None = None


@dataclass
class ModeScanState:
    """
    Remember how far we have already scanned in absolute sample index.
    This is the key difference from the old listener.
    """
    last_peak_abs: int = -10**18


def _resample_block(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """
    Resample one waveform from device sample rate to protocol sample rate.
    """
    x = np.asarray(x, dtype=np.float32)
    if len(x) == 0 or src_sr == dst_sr:
        return x

    g = math.gcd(int(src_sr), int(dst_sr))
    up = int(dst_sr // g)
    down = int(src_sr // g)

    y = resample_poly(x, up=up, down=down)
    return np.asarray(y, dtype=np.float32)


def _update_ring(ring: np.ndarray, block: np.ndarray) -> None:
    n = len(block)
    if n <= 0:
        return
    if n >= len(ring):
        ring[:] = block[-len(ring):]
        return

    ring[:-n] = ring[n:]
    ring[-n:] = block


def _chirp_score_at(x: np.ndarray, tpl: np.ndarray, start_idx: int) -> float:
    """
    Normalized chirp match score in [0, 1]-ish range.
    """
    if start_idx < 0 or start_idx + len(tpl) > len(x):
        return 0.0

    seg = np.asarray(x[start_idx:start_idx + len(tpl)], dtype=np.float32)
    if len(seg) != len(tpl):
        return 0.0

    denom = float(np.linalg.norm(seg) * np.linalg.norm(tpl) + 1e-12)
    if denom <= 1e-12:
        return 0.0

    return float(abs(np.dot(seg, tpl)) / denom)


def _decode_frame_near_peak(
    x: np.ndarray,
    coarse_peak: int,
    cfg: AcousticConfig,
    rt_cfg: RealtimeListenerConfig,
    chirp_tpl: np.ndarray,
) -> dict:
    """
    Around a coarse chirp peak:
    1) refine chirp start locally using normalized chirp score
    2) try several bit-phase offsets
    3) validate frame (CRC if enabled by cfg)
    """
    best_idx = int(coarse_peak)
    best_score = _chirp_score_at(x, chirp_tpl, best_idx)

    search = int(round(rt_cfg.refine_window_s * cfg.sr))
    step = max(1, int(rt_cfg.refine_step_samples))

    for off in range(-search, search + 1, step):
        idx = coarse_peak + off
        sc = _chirp_score_at(x, chirp_tpl, idx)
        if sc > best_score:
            best_score = sc
            best_idx = idx

    payload_start0 = best_idx + cfg.chirp_len
    nbits = cfg.frame_bits
    bit_len = cfg.bit_len

    best_try = {
        "ok": False,
        "reason": "frame_check_failed",
        "peak": int(best_idx),
        "score": float(best_score),
        "payload_start": int(payload_start0),
        "cmd": None,
        "seq": None,
        "frame_bytes": None,
        "phase": None,
    }

    phase_step = max(1, bit_len // max(1, rt_cfg.phase_div))
    for phase in range(0, bit_len, phase_step):
        start_idx = payload_start0 + phase
        bits = decode_bits_from(
            x=x,
            start_idx=start_idx,
            nbits=nbits,
            sr=cfg.sr,
            bit_dur=cfg.bit_dur,
            f0=cfg.f0,
            f1=cfg.f1,
        )
        if bits is None or len(bits) != nbits:
            continue

        frame_bytes = bits_to_bytes(bits, msb_first=cfg.msb_first)
        ok, cmd, seq = check_frame(frame_bytes, cfg)
        item = {
            "ok": bool(ok),
            "reason": None if ok else "frame_check_failed",
            "peak": int(best_idx),
            "score": float(best_score),
            "payload_start": int(start_idx),
            "cmd": int(cmd),
            "seq": int(seq),
            "frame_bytes": frame_bytes,
            "phase": int(phase),
        }
        if ok:
            return item

        best_try = item

    return best_try


def _mode_matches_cmd(mode: str, cmd: int) -> bool:
    if mode == "fast":
        return is_fast_cmd(cmd)
    if mode == "slow":
        return is_slow_cmd(cmd)
    return False


def _required_accept_min(mode: str, cmd: int, rt_cfg: RealtimeListenerConfig) -> int:
    if mode == "fast":
        return rt_cfg.fast_accept_min
    if cmd == STOP_CMD:
        return rt_cfg.stop_accept_min
    return rt_cfg.slow_accept_min


def _post_accept_holdoff_s(mode: str, cmd: int, rt_cfg: RealtimeListenerConfig) -> float:
    if mode == "fast":
        return rt_cfg.fast_post_accept_s
    if cmd == STOP_CMD:
        return rt_cfg.stop_post_accept_s
    return rt_cfg.slow_post_accept_s


def _chirp_thresh_for_mode(mode: str, rt_cfg: RealtimeListenerConfig) -> float:
    return rt_cfg.fast_chirp_thresh if mode == "fast" else rt_cfg.slow_chirp_thresh


def _accept_score_min_for_mode(mode: str, rt_cfg: RealtimeListenerConfig) -> float:
    return rt_cfg.fast_accept_score_min if mode == "fast" else 0.0


def _expected_repeat_offset_samples(cfg: AcousticConfig) -> int:
    """
    For fast:
    repeat offset = one whole frame duration + inter-frame gap
                  = silence_head + chirp + payload + gap
    """
    silence_head_len = getattr(
        cfg,
        "silence_head_len",
        int(round(float(getattr(cfg, "silence_head_s", 0.0)) * cfg.sr)),
    )
    gap_len = getattr(
        cfg,
        "gap_len",
        int(round(float(getattr(cfg, "gap_s", 0.0)) * cfg.sr)),
    )
    payload_len = int(cfg.frame_bits * cfg.bit_len)
    return int(silence_head_len + cfg.chirp_len + payload_len + gap_len)


def _is_expected_fast_repeat(
    first_abs_peak: int,
    second_abs_peak: int,
    cfg: AcousticConfig,
    rt_cfg: RealtimeListenerConfig,
) -> bool:
    expect = _expected_repeat_offset_samples(cfg)
    tol = int(round(rt_cfg.fast_repeat_tol_s * cfg.sr))
    delta = int(second_abs_peak) - int(first_abs_peak)
    return abs(delta - expect) <= tol


def _summarize_ok_frames(mode: str, ok_items: list[dict], rt_cfg: RealtimeListenerConfig) -> dict | None:
    """
    Choose the best decoded cmd/seq among valid frames.
    Fast / ordinary Slow: 1 frame is enough
    STOP: need stronger acceptance
    """
    if not ok_items:
        return None

    stats: dict[tuple[int, int], dict] = {}
    for item in ok_items:
        key = (int(item["cmd"]), int(item["seq"]))
        entry = stats.setdefault(
            key,
            {
                "count": 0,
                "best_score": float("-inf"),
                "best_item": None,
            },
        )
        entry["count"] += 1
        if float(item["score"]) > float(entry["best_score"]):
            entry["best_score"] = float(item["score"])
            entry["best_item"] = item

    best_key, best_entry = max(
        stats.items(),
        key=lambda kv: (int(kv[1]["count"]), float(kv[1]["best_score"])),
    )
    cmd, seq = best_key
    need = _required_accept_min(mode, cmd, rt_cfg)
    if int(best_entry["count"]) < need:
        return None

    return {
        "cmd": int(cmd),
        "seq": int(seq),
        "vote_count": int(best_entry["count"]),
        "best_score": float(best_entry["best_score"]),
        "best_item": best_entry["best_item"],
    }


def _collect_mode_candidate(
    wave: np.ndarray,
    mode: str,
    cfg: AcousticConfig,
    chirp_tpl: np.ndarray,
    rt_cfg: RealtimeListenerConfig,
    ring_start_abs: int,
    state: ModeScanState,
) -> dict | None:
    """
    Fast:
    - still allow single-frame accept
    - but only treat a second frame as the same packet if it falls inside
      the expected repeat window after the first frame

    Slow:
    - keep old summarization logic
    """
    peaks = find_topk_chirp_peaks(
        x=wave,
        chirp_tpl=chirp_tpl,
        sr=cfg.sr,
        k=rt_cfg.search_topk,
        min_gap_s=rt_cfg.min_gap_s,
        score_threshold=_chirp_thresh_for_mode(mode, rt_cfg),
        use_abs=True,
    )

    if rt_cfg.verbose_debug:
        top = ", ".join(f"({int(p)}, {float(s):.4f})" for p, s in peaks[:5])
        print(f"[{mode}] peaks={len(peaks)} top=[{top}]")

    if not peaks:
        return None

    max_phase_slack = cfg.bit_len
    frame_need_len = cfg.chirp_len + cfg.frame_bits * cfg.bit_len + max_phase_slack

    frame_results: list[dict] = []
    ok_items: list[dict] = []

    processed_abs_max = state.last_peak_abs

    for peak, raw_score in peaks:
        abs_peak = int(ring_start_abs + peak)

        if abs_peak <= state.last_peak_abs:
            continue

        if peak + frame_need_len > len(wave):
            continue

        processed_abs_max = max(processed_abs_max, abs_peak)

        item = _decode_frame_near_peak(
            x=wave,
            coarse_peak=peak,
            cfg=cfg,
            rt_cfg=rt_cfg,
            chirp_tpl=chirp_tpl,
        )
        item["abs_peak"] = int(abs_peak)
        item["raw_peak_score"] = float(raw_score)
        frame_results.append(item)

        if rt_cfg.verbose_debug:
            print(
                f"[{mode}] abs_peak={abs_peak} raw={raw_score:.4f} "
                f"ok={item['ok']} cmd={item['cmd']} seq={item['seq']} "
                f"score={item['score']:.4f} phase={item['phase']}"
            )

        if item["ok"] and _mode_matches_cmd(mode, int(item["cmd"])):
            ok_items.append(item)

    state.last_peak_abs = processed_abs_max

    if not frame_results:
        return None

    # -------------------------
    # fast: packet-aware pairing
    # -------------------------
    if mode == "fast":
        ok_fast = [it for it in ok_items if int(it["cmd"]) >= 0]
        if not ok_fast:
            return None

        ok_fast.sort(key=lambda it: int(it["abs_peak"]))

        best_candidate = None

        for i, first in enumerate(ok_fast):
            partner = None
            for second in ok_fast[i + 1:]:
                if int(second["abs_peak"]) <= int(first["abs_peak"]):
                    continue

                expect = _expected_repeat_offset_samples(cfg)
                tol = int(round(rt_cfg.fast_repeat_tol_s * cfg.sr))
                delta = int(second["abs_peak"]) - int(first["abs_peak"])
                if delta > expect + tol:
                    break

                if (
                    _is_expected_fast_repeat(
                        int(first["abs_peak"]),
                        int(second["abs_peak"]),
                        cfg,
                        rt_cfg,
                    )
                    and int(second["cmd"]) == int(first["cmd"])
                    and int(second["seq"]) == int(first["seq"])
                ):
                    partner = second
                    break

            vote_count = 2 if partner is not None else 1
            need = _required_accept_min(mode, int(first["cmd"]), rt_cfg)
            if vote_count < need:
                continue

            best_item = first
            best_score = float(first["score"])
            if partner is not None and float(partner["score"]) > best_score:
                best_item = partner
                best_score = float(partner["score"])

            if best_score < _accept_score_min_for_mode(mode, rt_cfg):
                continue

            cand = {
                "mode": mode,
                "cfg": cfg,
                "cmd": int(first["cmd"]),
                "seq": int(first["seq"]),
                "vote_count": int(vote_count),
                "vote_total": int(vote_count),
                "best_score": float(best_score),
                "frames": frame_results,
                "decoded_ok": [(int(it["cmd"]), int(it["seq"])) for it in ok_fast],
                "best_item": best_item,
            }

            if best_candidate is None:
                best_candidate = cand
            else:
                if (
                    int(cand["vote_count"]) > int(best_candidate["vote_count"])
                    or (
                        int(cand["vote_count"]) == int(best_candidate["vote_count"])
                        and float(cand["best_score"]) > float(best_candidate["best_score"])
                    )
                ):
                    best_candidate = cand

        return best_candidate

    # -------------------------
    # slow: keep old behavior
    # -------------------------
    summary = _summarize_ok_frames(mode, ok_items, rt_cfg)
    if summary is None:
        return None

    return {
        "mode": mode,
        "cfg": cfg,
        "cmd": int(summary["cmd"]),
        "seq": int(summary["seq"]),
        "vote_count": int(summary["vote_count"]),
        "vote_total": len(ok_items),
        "best_score": float(summary["best_score"]),
        "frames": frame_results,
        "decoded_ok": [(int(it["cmd"]), int(it["seq"])) for it in ok_items],
        "best_item": summary["best_item"],
    }


def _choose_best_candidate(candidates: list[dict | None]) -> dict | None:
    valid = [c for c in candidates if c is not None]
    if not valid:
        return None

    return max(
        valid,
        key=lambda c: (
            int(c["vote_count"]),
            float(c["best_score"]),
            len(c["decoded_ok"]),
        ),
    )


def listen_forever(
    fast_cfg: AcousticConfig = FAST_CONFIG,
    slow_cfg: AcousticConfig = SLOW_CONFIG,
    rt_cfg: RealtimeListenerConfig = RealtimeListenerConfig(),
    device: int | None = None,
    on_trigger: Callable[[int, int, dict], None] | None = None,
) -> None:
    """
    Realtime acoustic listener for both fast and slow protocols.

    Core difference from the old version:
    it is stateful and only processes NEW chirp peaks.
    """
    if fast_cfg.sr != slow_cfg.sr:
        raise ValueError("fast_cfg.sr and slow_cfg.sr must match")

    sr = fast_cfg.sr
    input_sr = sr if rt_cfg.input_sr is None else int(rt_cfg.input_sr)

    # decode/protocol domain
    hop = max(1, int(round(rt_cfg.hop_s * sr)))
    ring_len = max(hop, int(round(rt_cfg.ring_s * sr)))
    ring = np.zeros(ring_len, dtype=np.float32)

    # device/capture domain
    hop_in = max(1, int(round(rt_cfg.hop_s * input_sr)))
    raw_ring_len = max(hop_in, int(round(rt_cfg.ring_s * input_sr)))
    raw_ring = np.zeros(raw_ring_len, dtype=np.float32)

    fast_tpl = make_chirp_template(
        sr=fast_cfg.sr,
        chirp_dur=fast_cfg.chirp_dur,
        f0=fast_cfg.chirp_f0,
        f1=fast_cfg.chirp_f1,
        fade_len=fast_cfg.fade_len,
    )
    slow_tpl = make_chirp_template(
        sr=slow_cfg.sr,
        chirp_dur=slow_cfg.chirp_dur,
        f0=slow_cfg.chirp_f0,
        f1=slow_cfg.chirp_f1,
        fade_len=slow_cfg.fade_len,
    )

    fast_state = ModeScanState()
    slow_state = ModeScanState()

    capture_dir = Path(rt_cfg.capture_dir)
    if rt_cfg.save_capture:
        capture_dir.mkdir(parents=True, exist_ok=True)

    print("=== Realtime acoustic listener (stateful) ===")
    print(
        f"sr={sr}, input_sr={input_sr}, hop={rt_cfg.hop_s}s, ring={rt_cfg.ring_s}s, "
        f"fast_thresh={rt_cfg.fast_chirp_thresh}, slow_thresh={rt_cfg.slow_chirp_thresh}, "
        f"fast_accept_min={rt_cfg.fast_accept_min}, "
        f"slow_accept_min={rt_cfg.slow_accept_min}, "
        f"stop_accept_min={rt_cfg.stop_accept_min}, "
        f"fast_holdoff={rt_cfg.fast_post_accept_s}s, "
        f"slow_holdoff={rt_cfg.slow_post_accept_s}s, "
        f"stop_holdoff={rt_cfg.stop_post_accept_s}s"
    )
    print(
        "fast_chirp="
        f"{fast_cfg.chirp_f0:.0f}->{fast_cfg.chirp_f1:.0f} dur={fast_cfg.chirp_dur:.3f}s | "
        "slow_chirp="
        f"{slow_cfg.chirp_f0:.0f}->{slow_cfg.chirp_f1:.0f} dur={slow_cfg.chirp_dur:.3f}s"
    )
    if device is not None:
        print(f"input_device={device}")
    print("Press Ctrl+C to stop.\n")

    last_debug_t = 0.0
    suppress_until = 0.0
    sample_clock = 0  # absolute sample count in decode/protocol domain

    warmup_until_samples = int(round(rt_cfg.startup_warmup_s * sr))

    try:
        with open_input_stream(
            sr=input_sr,
            blocksize=hop_in,
            device=device,
            dtype="float32",
            channels=1,
        ) as stream:
            while True:
                raw_block, _overflowed = stream.read(hop_in)
                raw_block = np.asarray(raw_block, dtype=np.float32).reshape(-1)

                mic_level = float(np.max(np.abs(raw_block))) if len(raw_block) else 0.0

                # maintain raw 48k ring
                _update_ring(raw_ring, raw_block)

                # resample the whole raw ring into the 16k protocol domain
                ring_rs = _resample_block(raw_ring, src_sr=input_sr, dst_sr=sr)

                # keep fixed-length decode ring and preserve the newest samples
                if len(ring_rs) >= ring_len:
                    ring[:] = ring_rs[-ring_len:]
                else:
                    ring[:] = 0.0
                    ring[-len(ring_rs):] = ring_rs

                # advance decode-domain clock by one protocol hop
                sample_clock += hop
                ring_start_abs = int(sample_clock - len(ring))

                now_wall = float(
                    np.round(
                        np.float64(
                            np.datetime64("now").astype("datetime64[ms]").astype(int)
                        ) / 1000.0,
                        3,
                    )
                )
                now_mono = time.monotonic()

                if sample_clock < warmup_until_samples:
                    if rt_cfg.clear_ring_after_accept:
                        ring[:] = 0.0
                        raw_ring[:] = 0.0
                    fast_state.last_peak_abs = sample_clock
                    slow_state.last_peak_abs = sample_clock
                    last_debug_t = now_wall
                    continue

                # hard suppress after accepted trigger:
                # ignore the tail of the same wav
                if now_mono < suppress_until:
                    if rt_cfg.clear_ring_after_accept:
                        ring[:] = 0.0
                        raw_ring[:] = 0.0
                    fast_state.last_peak_abs = sample_clock
                    slow_state.last_peak_abs = sample_clock

                    if now_wall - last_debug_t >= rt_cfg.debug_every_s:
                        remain = max(0.0, suppress_until - now_mono)
                        clip_tag = " CLIP!" if mic_level >= rt_cfg.clip_warn_level else ""
                        print(
                            f"[dbg] mic={mic_level:.4f}{clip_tag} suppressed={remain:.2f}s "
                            f"fast_ready=False fast_score=0.0000 "
                            f"slow_ready=False slow_score=0.0000 chosen=none"
                        )
                        last_debug_t = now_wall
                    continue

                fast_candidate = _collect_mode_candidate(
                    wave=ring,
                    mode="fast",
                    cfg=fast_cfg,
                    chirp_tpl=fast_tpl,
                    rt_cfg=rt_cfg,
                    ring_start_abs=ring_start_abs,
                    state=fast_state,
                )
                slow_candidate = _collect_mode_candidate(
                    wave=ring,
                    mode="slow",
                    cfg=slow_cfg,
                    chirp_tpl=slow_tpl,
                    rt_cfg=rt_cfg,
                    ring_start_abs=ring_start_abs,
                    state=slow_state,
                )

                chosen = _choose_best_candidate([fast_candidate, slow_candidate])

                if now_wall - last_debug_t >= rt_cfg.debug_every_s:
                    fast_ready = fast_candidate is not None
                    slow_ready = slow_candidate is not None
                    fast_score = 0.0 if fast_candidate is None else float(fast_candidate["best_score"])
                    slow_score = 0.0 if slow_candidate is None else float(slow_candidate["best_score"])
                    chosen_mode = "none" if chosen is None else str(chosen["mode"])
                    clip_tag = " CLIP!" if mic_level >= rt_cfg.clip_warn_level else ""
                    print(
                        f"[dbg] mic={mic_level:.4f}{clip_tag} "
                        f"fast_ready={fast_ready} fast_score={fast_score:.4f} "
                        f"slow_ready={slow_ready} slow_score={slow_score:.4f} "
                        f"chosen={chosen_mode}"
                    )

                    if rt_cfg.save_debug_ring:
                        write_wav(rt_cfg.debug_ring_path, ring, sr)

                    last_debug_t = now_wall

                if chosen is None:
                    continue

                info = {
                    "mode": chosen["mode"],
                    "cmd": int(chosen["cmd"]),
                    "seq": int(chosen["seq"]),
                    "vote_count": int(chosen["vote_count"]),
                    "vote_total": int(chosen["vote_total"]),
                    "best_score": float(chosen["best_score"]),
                    "frames": chosen["frames"],
                    "decoded_ok": chosen["decoded_ok"],
                    "fast_candidate": fast_candidate,
                    "slow_candidate": slow_candidate,
                }

                print(
                    f"✅ trigger accepted: mode={chosen['mode']} "
                    f"cmd=0x{chosen['cmd']:02X} ({cmd_name(chosen['cmd'])}) "
                    f"seq={chosen['seq']} "
                    f"(votes {chosen['vote_count']}/{max(1, chosen['vote_total'])}, "
                    f"score={chosen['best_score']:.4f})"
                )

                if rt_cfg.save_capture:
                    stamp = np.datetime64("now", "s").astype(str).replace(":", "-")
                    out_path = capture_dir / f"{rt_cfg.capture_prefix}_{stamp}.wav"
                    write_wav(str(out_path), ring, sr)
                    print(f"   saved capture: {out_path}")

                if on_trigger is not None:
                    on_trigger(chosen["cmd"], chosen["seq"], info)

                suppress_until = now_mono + _post_accept_holdoff_s(
                    chosen["mode"],
                    chosen["cmd"],
                    rt_cfg,
                )

                # after accept: forget everything up to "now"
                fast_state.last_peak_abs = sample_clock
                slow_state.last_peak_abs = sample_clock

                if rt_cfg.clear_ring_after_accept:
                    ring[:] = 0.0
                    raw_ring[:] = 0.0

    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> None:
    rt_cfg = RealtimeListenerConfig(
        fast_accept_min=1,
        slow_accept_min=1,
        stop_accept_min=2,
        clear_ring_after_accept=True,
        fast_post_accept_s=1.25,
        slow_post_accept_s=2.0,
        stop_post_accept_s=3.0,
        fast_chirp_thresh=0.03,
        slow_chirp_thresh=0.10,
        fast_repeat_tol_s=0.05,
        clip_warn_level=0.90,
        fast_accept_score_min=0.0,
        startup_warmup_s=1.5,
        input_sr=48000,
        verbose_debug=False,
    )
    listen_forever(
        fast_cfg=FAST_CONFIG,
        slow_cfg=SLOW_CONFIG,
        rt_cfg=rt_cfg,
        device=0,
        on_trigger=None,
    )


if __name__ == "__main__":
    main()
```

如果这版还是不行，直接把你原来的文件恢复回去。

最方便的是：

```
cp src/acoustic_comm/rx/realtime_listener.py src/acoustic_comm/rx/realtime_listener.py.bak
```

替换前先备份一份。

可以啊我感觉很完美，还有什么需要注意的吗

Thought

很不错，这版已经进入“可用”状态了。

从你这段运行结果看，几个信号都很好：

* fast 和 slow 都已经能触发
* 触发分数大致在 `0.36 ~ 0.41`，比较稳定
* 空闲时 `mic` 基本在 `0.01 ~ 0.02` 左右，没有明显乱触发
* 触发后 suppress 也在正常工作

现在最需要注意的，不是继续大改，而是**别把现在这个能跑的版本再调坏了**。

### 你现在最该做的几件事

先把当前可用版本备份一份。

尤其是 `src/acoustic_comm/rx/realtime_listener.py`，因为这是你现在最关键的工作版本。

```
cp src/acoustic_comm/rx/realtime_listener.py src/acoustic_comm/rx/realtime_listener_working.py
```

然后把这次成功对应的参数记下来：

* `input_sr=48000`
* `device=0`
* `fast_thresh=0.03`
* `slow_thresh=0.1`
* `fast_post_accept_s=1.25`
* `slow_post_accept_s=2.0`
* `stop_post_accept_s=3.0`

### 现场使用时要特别注意的点

第一，**连续发命令不要太快**。

你现在配置里有 holdoff，所以：

* fast 触发后大约 `1.25s` 内会 suppress
* slow 触发后大约 `2.0s` 内会 suppress
* stop 是 `3.0s`

也就是说，如果你刚播完一个 fast，立刻再播下一个，很可能第二个会被你自己的 suppress 吃掉。这个不是 bug，是你现在的防重复触发策略。

第二，**STOP 要单独做专项测试**。

你当前代码里 `stop_accept_min=2`，也就是 stop 比普通命令更严格。你这次日志里已经验证了 fast/slow 的多条普通命令，但还没看到 stop 的现场成功样本，所以 stop 最好单独测距离、噪声、电机干扰和最坏角度。

第三，**先别继续降阈值**。

现在已经能稳定检出，而且空闲时没有明显误触发，再往下压阈值，收益通常不大，误检风险会上升。

第四，**不要把 `input_sr=48000` 误当成协议改成 48k 了**。

你现在只是“设备 0 用 48k 采进来，再回到 16k 协议域里解码”。

也就是说：

* `constants.py` 里的协议还是 16k
* 你的 wav 还是原来的协议 wav
* 这次成功不代表要去重生全部音频

### 我建议你补做的验收

你现在最值钱的不是继续改代码，而是做一轮固定流程验收：

* 八条命令各播 10 次，记成功率
* fast 和 slow 分开记
* 单独测 stop
* 再测两三个现场距离
* 再加一组“机器人电机开着”的测试

尤其是 stop，必须单独看。

### 一个很实用的小建议

保留两份 listener：

* `realtime_listener_working.py`：现在这个已验证版本
* `realtime_listener.py`：以后继续实验的版本

这样以后再调，不会把现在能跑的版本弄丢。

总体上，你现在这版已经说明方向是对的：

**协议不用改，音频不用改，问题主要就是监听入口和设备适配。**

如果你愿意，我下一条可以直接帮你列一份“赛前 5 分钟快速检查清单”。