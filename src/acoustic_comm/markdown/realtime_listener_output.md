(acoustic_comm) zaredanrove@zaredanrove:~/acoustic_comm$  conda activate acoustic_comm
(acoustic_comm) zaredanrove@zaredanrove:~/acoustic_comm$ PYTHONPATH=src python -m acoustic_comm.rx.realtime_listener_working
=== Realtime acoustic listener (stateful) ===
sr=16000, input_sr=48000, hop=0.02s, ring=3.0s, fast_thresh=0.03, slow_thresh=0.1, fast_accept_min=1, slow_accept_min=1, stop_accept_min=2, fast_holdoff=1.25s, slow_holdoff=2.0s, stop_holdoff=3.0s
fast_chirp=1200->3200 dur=0.060s | slow_chirp=1200->3200 dur=0.080s
input_device=0
Press Ctrl+C to stop.

[dbg] mic=0.0295 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0161 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0186 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.1382 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
✅ trigger accepted: mode=fast cmd=0xE1 (梅林：前三个梅林方块放好后，R1完全拿走，R2再上梅林) seq=0 (votes 1/1, score=0.4007)
[dbg] mic=0.0145 suppressed=0.33s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0204 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0192 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0174 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
✅ trigger accepted: mode=fast cmd=0x27 (武馆：R2接到R1离开武馆指令，在R1离开后进入树林) seq=0 (votes 1/1, score=0.3975)
[dbg] mic=0.1191 suppressed=1.07s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0167 suppressed=0.07s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0127 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0192 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.2509 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
✅ trigger accepted: mode=fast cmd=0x72 (梅林：肉眼判断R2拿够KFS，R1进入对抗区后，R2也离开梅林) seq=0 (votes 1/1, score=0.3861)
[dbg] mic=0.0389 suppressed=0.75s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0151 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0266 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0192 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0500 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
✅ trigger accepted: mode=fast cmd=0x8A (武馆：R2在端头等待，收到指令后开始拼接) seq=0 (votes 1/1, score=0.3889)
[dbg] mic=0.0162 suppressed=0.27s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0173 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0210 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0188 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0259 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0953 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
✅ trigger accepted: mode=slow cmd=0x5C (武馆：拼接结束后判断成功，随后进行下一个端头动作) seq=0 (votes 1/1, score=0.4336)
[dbg] mic=0.0536 suppressed=1.56s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0158 suppressed=0.56s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0172 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0261 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0200 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0882 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
✅ trigger accepted: mode=slow cmd=0x39 (对抗区：R2站到R1上将KFS放在九宫格顶层) seq=0 (votes 1/1, score=0.4162)
[dbg] mic=0.0791 suppressed=1.72s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0248 suppressed=0.72s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0157 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0194 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0182 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.1161 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
✅ trigger accepted: mode=slow cmd=0x95 (全场：R2需要重试，由R1给出指令) seq=0 (votes 1/1, score=0.4431)
[dbg] mic=0.1173 suppressed=1.24s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0139 suppressed=0.24s fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
[dbg] mic=0.0151 fast_ready=False fast_score=0.0000 slow_ready=False slow_score=0.0000 chosen=none
^C
Stopped.
(acoustic_comm) zaredanrove@zaredanrove:~/acoustic_comm$ 