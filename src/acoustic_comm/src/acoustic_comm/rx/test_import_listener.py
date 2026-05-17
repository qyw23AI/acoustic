from acoustic_comm.rx.listener_api import RealtimeListener
from acoustic_comm.rx.realtime_listener_working import RealtimeListenerConfig


def handle_detection(event):
    print(">>> event:", event.to_dict())


listener = RealtimeListener(
    rt_cfg=RealtimeListenerConfig(input_sr=48000),
    input_device=0,
)

listener.run_forever(on_detection=handle_detection)