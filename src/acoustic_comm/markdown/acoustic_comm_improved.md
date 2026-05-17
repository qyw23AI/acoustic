我有一个实时声学通信系统（Python 实现），结构如下：

* 使用 chirp（1200→3200 Hz）做同步
* 使用 2-FSK（1500 / 2500 Hz）做 payload
* 协议采样率：16000 Hz
* 实际输入：设备采样率 48000 Hz，实时重采样到 16000 Hz
* Fast / Slow 双链路
* realtime\_listener 是 stateful：

* 只处理新的 chirp 峰
* chirp refine + 多 phase 解码
* Fast 支持单帧 accept + repeat 结构约束
* accept 后 clear ring + suppress

当前系统已经做到：

* 不再双触发
* 漏检很少
* 对音量变化和一定程度削波有鲁棒性

我现在想在**不改变现有协议**的前提下，继续增强鲁棒性。请你只基于我现有架构做**最小侵入式增强**，不要重写整套系统。

---

## 目标 1：自适应阈值（环境噪声变化）

背景：

目前 chirp 检测使用固定阈值（例如 fast\_chirp\_thresh / slow\_chirp\_thresh）。这在安静环境下可以，但在现场噪声、混响、底噪变化较大时，固定阈值可能导致：

* 安静环境：阈值偏高，漏检
* 嘈杂环境：阈值偏低，误检
* 不同场地需要手工重新调参数

需求：

1. 让 chirp 检测阈值能随环境噪声动态调整
2. 仍然保持实时性
3. 不引入复杂训练或机器学习方案
4. 尽量保持现有 find\_topk\_chirp\_peaks / realtime\_listener 结构不大改
5. 最好区分：

* fast 阈值自适应
* slow 阈值自适应

希望你回答：

* 推荐采用哪种自适应阈值方法：

* 基于滑动噪声底估计
* 基于分位数 / percentile
* 基于 EMA / IIR 的背景分数跟踪
* 其他更合适的方法
* 阈值应建立在哪个量上：

* chirp correlation score
* raw energy
* band-limited energy
* 应该如何避免“刚触发后，阈值被目标信号本身抬高”
* 是否需要 separate noise floor for fast / slow
* 建议放在什么位置：

* chirp peak search 前
* peak score 后
* 还是作为 score\_threshold 的动态更新

请给出：

* 明确的工程方案
* 参数建议（滑动时间常数、percentile、margin）
* Python 示例代码
* 应插入 realtime\_listener 的具体位置
* 说明可能副作用（响应慢、阈值漂移、短时误检等）

---

## 目标 2：输入端 AGC / 限幅（防削波）

需求：

1. 防止麦克风输入过大导致 clipping
2. 在不破坏 chirp 和 FSK 判决的前提下进行动态增益控制
3. 不引入明显时延
4. 不明显改变 chirp 相关匹配结果
5. 不明显破坏 FSK 在 1500 / 2500 Hz 的能量判决

希望你回答：

* 应该选用哪种 AGC 方案：

* peak-based
* RMS-based
* limiter
* compressor
* soft clipping
* 推荐的实现位置：

* raw\_block（重采样前）
* block（重采样后）
* 或两级结构
* 是否建议只做 limiter，而不做 full AGC
* 推荐参数范围：

* attack / release
* target RMS / target peak
* limiter threshold
* 是否需要 fast / slow 区分不同策略

请给出：

* 明确设计方案
* Python 示例代码（可嵌入 realtime\_listener）
* 说明对 chirp 检测和 FSK 解码的影响
* 说明如何避免 AGC 本身造成触发抖动

---

## 目标 3：频偏跟踪（frequency offset tracking）

背景：

* 实际扬声器 / 麦克风 / 环境可能引入频偏
* 当前 FSK 使用固定 f0=1500 Hz，f1=2500 Hz
* chirp 用于同步，但目前没有利用 chirp 估计频偏

需求：

1. 利用 chirp 或 payload 估计频偏（Δf）
2. 在 decode\_bits\_from 前进行补偿，或等价地修正检测频率
3. 保持实时性
4. 不改变 frame 结构
5. 不大改现有协议

希望你回答：

* 推荐方法：

* chirp-based 频偏估计
* 基于 payload 的频偏估计
* 基于能量中心漂移
* 是否建议：

* 每帧估计
* 滑动平均
* IIR 跟踪
* 如何补偿：

* 频率平移（mixing）
* 或调整解码频率 f0 / f1
* 频偏估计应该放在：

* coarse peak 后
* refine 后
* decode 前
* 还是 frame 成功后回写跟踪器

请给出：

* 具体算法步骤
* Python 示例代码
* 嵌入 `_decode_frame_near_peak` 或其周边的最小改法
* 参数建议（平滑系数 / 频偏范围 / 更新速率）
* 说明可能副作用（错误跟踪、过补偿、实时性开销）

---

## 限制条件

* 不改变 protocol/constants.py
* 不改变 tx 侧 wav
* 不改变现有命令表
* 不显著增加 CPU 开销
* 不引入超过 20ms 的额外延迟
* 优先保持现有 realtime\_listener 架构，只做增量改进

---

## 输出要求

请你：

1. 分别给出“自适应阈值 / AGC / 频偏跟踪”的工程可落地方案
2. 明确说明每项改动应插入 realtime\_listener 的哪一段
3. 给出关键 Python 代码，不要只给伪代码
4. 说明每个参数为什么这样选
5. 说明三者之间的关系，以及推荐的落地顺序
6. 明确指出哪部分最值得先做，哪部分可以后做

重点是：**基于我现有的 stateful realtime\_listener，做最小侵入式增强鲁棒性，而不是重写系统。**