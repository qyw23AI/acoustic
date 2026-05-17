from __future__ import annotations

import threading
from typing import Optional

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from std_msgs.msg import UInt8
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue

from acoustic_bridge_msgs.msg import AcousticDetection, AcousticHeartbeat
from acoustic_comm.rx.listener_api import RealtimeListener, DetectionEvent


class AcousticBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('acoustic_bridge')

        # -----------------------------
        # Parameters
        # -----------------------------
        self.declare_parameter('publish_detection_topic', '/acoustic_comm/detection')
        self.declare_parameter('publish_heartbeat_topic', '/acoustic_comm/heartbeat')
        self.declare_parameter('diagnostics_topic', '/diagnostics')
        self.declare_parameter('heartbeat_hz', 2.0)
        self.declare_parameter('input_device', -1)
        self.declare_parameter('print_detection', False)
        self.declare_parameter('device_label', 'unknown')
        self.declare_parameter('listener_version', 'listener_api_v1')
        self.declare_parameter('enable_repeat_guard', False)
        self.declare_parameter('repeat_guard_window_sec', 1.0)
        self.declare_parameter('publish_ecu_trigger_topic', '/acoustic_comm/trigger_to_ecu')

        detection_topic = self.get_parameter(
            'publish_detection_topic'
        ).get_parameter_value().string_value
        heartbeat_topic = self.get_parameter(
            'publish_heartbeat_topic'
        ).get_parameter_value().string_value
        diagnostics_topic = self.get_parameter(
            'diagnostics_topic'
        ).get_parameter_value().string_value
        ecu_trigger_topic = self.get_parameter(
            'publish_ecu_trigger_topic'
        ).get_parameter_value().string_value
        heartbeat_hz = self.get_parameter(
            'heartbeat_hz'
        ).get_parameter_value().double_value
        input_device = self.get_parameter(
            'input_device'
        ).get_parameter_value().integer_value
        print_detection = self.get_parameter(
            'print_detection'
        ).get_parameter_value().bool_value
        self._device_label = self.get_parameter(
            'device_label'
        ).get_parameter_value().string_value
        self._listener_version = self.get_parameter(
            'listener_version'
        ).get_parameter_value().string_value
        self._enable_repeat_guard = self.get_parameter(
            'enable_repeat_guard'
        ).get_parameter_value().bool_value
        self._repeat_guard_window_sec = self.get_parameter(
            'repeat_guard_window_sec'
        ).get_parameter_value().double_value

        # -----------------------------
        # Publishers
        # -----------------------------
        self._detection_pub = self.create_publisher(
            AcousticDetection,
            detection_topic,
            10,
        )
        self._heartbeat_pub = self.create_publisher(
            AcousticHeartbeat,
            heartbeat_topic,
            10,
        )
        self._diagnostics_pub = self.create_publisher(
            DiagnosticArray,
            diagnostics_topic,
            10,
        )
        self._ecu_trigger_pub = self.create_publisher(
            UInt8,
            ecu_trigger_topic,
            10,
        )

        # -----------------------------
        # Runtime state
        # -----------------------------
        self._listener: Optional[RealtimeListener] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._shutdown_requested = False
        self._external_stop_requested = False
        self._external_stop_reason = ''

        self._event_seq = 0
        self._restart_count = 0

        self._last_input_level = 0.0
        self._last_score_raw = 0.0
        self._last_mode = ''
        self._last_cmd_id = 0
        self._last_detection_time = None

        self._last_repeat_key = None
        self._last_repeat_time_ns = None

        # -----------------------------
        # Listener
        # -----------------------------
        listener_input_device = None if input_device < 0 else int(input_device)

        self._listener = RealtimeListener(
            input_device=listener_input_device,
            print_detection=print_detection,
        )

        self._listener_thread = threading.Thread(
            target=self._run_listener,
            name='acoustic_listener_thread',
            daemon=True,
        )
        self._listener_thread.start()

        # -----------------------------
        # Timers
        # -----------------------------
        heartbeat_period = 0.5
        if heartbeat_hz > 0.0:
            heartbeat_period = 1.0 / heartbeat_hz

        self._heartbeat_timer = self.create_timer(
            heartbeat_period,
            self._publish_heartbeat,
        )
        self._diagnostics_timer = self.create_timer(
            heartbeat_period,
            self._publish_diagnostics,
        )
        self._stop_check_timer = self.create_timer(
            0.1,
            self._check_external_stop,
        )

        # -----------------------------
        # Service
        # -----------------------------
        self._stop_service = self.create_service(
            Trigger,
            '/acoustic_bridge/stop',
            self._handle_stop_service,
        )

        self._safe_log(
            'info',
            'Acoustic bridge started. '
            f'detection_topic={detection_topic}, '
            f'heartbeat_topic={heartbeat_topic}, '
            f'input_device={listener_input_device}, '
            f'device_label={self._device_label}',
        )

    def _safe_log(self, level: str, text: str) -> None:
        try:
            if rclpy.ok():
                logger = self.get_logger()
                if level == 'info':
                    logger.info(text)
                elif level == 'warn':
                    logger.warning(text)
                elif level == 'error':
                    logger.error(text)
                else:
                    logger.info(text)
            else:
                print(f'[acoustic_bridge] {text}')
        except Exception:
            print(f'[acoustic_bridge] {text}')

    # ------------------------------------------------------------------
    # Listener thread
    # ------------------------------------------------------------------
    def _run_listener(self) -> None:
        try:
            assert self._listener is not None
            self._safe_log('info', 'Starting RealtimeListener.run_forever()')
            self._listener.run_forever(on_detection=self._on_detection)
            self._safe_log('info', 'RealtimeListener.run_forever() exited')
        except Exception as exc:
            self._safe_log('error', f'Listener thread crashed: {exc}')

    # ------------------------------------------------------------------
    # Detection callback
    # ------------------------------------------------------------------
    def _on_detection(self, event: DetectionEvent) -> None:
        now = self.get_clock().now()
        now_ns = now.nanoseconds

        self._last_input_level = float(event.input_level)
        self._last_score_raw = float(event.score_raw)
        self._last_mode = str(event.mode)
        self._last_cmd_id = int(event.cmd_id)
        self._last_detection_time = now

        repeat_suppressed = False

        if self._enable_repeat_guard:
            repeat_key = (int(event.cmd_id), str(event.mode))
            if (
                self._last_repeat_key == repeat_key
                and self._last_repeat_time_ns is not None
            ):
                dt_sec = (now_ns - self._last_repeat_time_ns) / 1e9
                if dt_sec < self._repeat_guard_window_sec:
                    repeat_suppressed = True

            self._last_repeat_key = repeat_key
            self._last_repeat_time_ns = now_ns

        msg = AcousticDetection()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = ''

        msg.valid = bool(event.valid)
        msg.event_seq = self._event_seq
        msg.source = str(event.source)
        msg.mode = str(event.mode)
        msg.cmd_id = int(event.cmd_id)
        msg.cmd_hex = str(event.cmd_hex)
        msg.cmd_name = str(event.cmd_name)
        msg.score_raw = float(event.score_raw)
        msg.confidence = float(event.confidence)
        msg.input_level = float(event.input_level)
        msg.is_stop_command = bool(event.is_stop_command)
        msg.is_repeat_suppressed = repeat_suppressed
        msg.listener_version = self._listener_version
        msg.note = str(event.note)

        self._event_seq += 1

        self._detection_pub.publish(msg)
        if msg.valid and (not msg.is_repeat_suppressed) and (not msg.is_stop_command):
            trigger = UInt8()
            trigger.data = 1
            self._ecu_trigger_pub.publish(trigger)
            self._safe_log(
                'info',
                f'Published ECU trigger signal on acoustic detection, cmd={msg.cmd_hex}',
            )

        self._safe_log(
            'info',
            'Published detection: '
            f'mode={msg.mode} '
            f'cmd={msg.cmd_hex} '
            f'name={msg.cmd_name} '
            f'score={msg.score_raw:.4f} '
            f'input_level={msg.input_level:.4f} '
            f'repeat_suppressed={msg.is_repeat_suppressed}',
        )

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------
    def _publish_heartbeat(self) -> None:
        now = self.get_clock().now()

        listener_running = False
        if self._listener is not None:
            listener_running = bool(self._listener.is_running)

        msg = AcousticHeartbeat()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = ''

        msg.alive = not self._shutdown_requested
        msg.listener_running = listener_running
        msg.audio_ok = listener_running
        msg.clipping = False
        msg.input_level = float(self._last_input_level)
        msg.last_score_raw = float(self._last_score_raw)
        msg.last_mode = str(self._last_mode)
        msg.last_cmd_id = int(self._last_cmd_id)

        if self._external_stop_requested:
            msg.state = 'stopping'
        elif listener_running:
            msg.state = 'running'
        else:
            msg.state = 'stopped'

        msg.device = self._device_label
        msg.restart_count = int(self._restart_count)

        self._heartbeat_pub.publish(msg)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def _publish_diagnostics(self) -> None:
        now = self.get_clock().now().to_msg()

        listener_running = False
        if self._listener is not None:
            listener_running = bool(self._listener.is_running)

        status = DiagnosticStatus()
        status.name = 'acoustic_bridge'
        status.hardware_id = self._device_label

        if self._external_stop_requested:
            status.level = DiagnosticStatus.WARN
            status.message = 'external stop requested'
        elif listener_running:
            status.level = DiagnosticStatus.OK
            status.message = 'listener running'
        else:
            status.level = DiagnosticStatus.WARN
            status.message = 'listener not running'

        status.values = [
            KeyValue(key='device', value=self._device_label),
            KeyValue(key='listener_version', value=self._listener_version),
            KeyValue(key='listener_running', value=str(listener_running)),
            KeyValue(key='external_stop_requested', value=str(self._external_stop_requested)),
            KeyValue(key='external_stop_reason', value=str(self._external_stop_reason)),
            KeyValue(key='last_mode', value=str(self._last_mode)),
            KeyValue(key='last_cmd_id', value=str(self._last_cmd_id)),
            KeyValue(key='last_score_raw', value=f'{self._last_score_raw:.6f}'),
            KeyValue(key='last_input_level', value=f'{self._last_input_level:.6f}'),
            KeyValue(key='restart_count', value=str(self._restart_count)),
        ]

        arr = DiagnosticArray()
        arr.header.stamp = now
        arr.status.append(status)

        self._diagnostics_pub.publish(arr)

    # ------------------------------------------------------------------
    # Stop service
    # ------------------------------------------------------------------
    def _handle_stop_service(self, request, response):
        del request

        if self._shutdown_requested or self._external_stop_requested:
            response.success = True
            response.message = 'acoustic_bridge stop already requested'
            return response

        self._external_stop_requested = True
        self._external_stop_reason = 'service:/acoustic_bridge/stop'
        self._safe_log('warn', 'External stop requested via /acoustic_bridge/stop')

        response.success = True
        response.message = 'acoustic_bridge stop accepted'
        return response

    def _check_external_stop(self) -> None:
        if not self._external_stop_requested:
            return

        self._safe_log(
            'warn',
            f'Processing external stop request, reason={self._external_stop_reason}',
        )

        self.shutdown_bridge()

        try:
            self.destroy_node()
        except Exception:
            pass

        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def shutdown_bridge(self) -> None:
        if self._shutdown_requested:
            return

        self._shutdown_requested = True
        self._safe_log('info', 'Shutting down acoustic bridge...')

        if self._listener is not None:
            try:
                self._safe_log('info', 'Calling listener.stop()')
                self._listener.stop()
            except Exception as exc:
                self._safe_log('error', f'listener.stop() failed: {exc}')

        if self._listener_thread is not None:
            self._listener_thread.join(timeout=5.0)
            if self._listener_thread.is_alive():
                self._safe_log('warn', 'Listener thread did not exit within timeout.')
            else:
                self._safe_log('info', 'Listener thread joined successfully.')

    def destroy_node(self) -> bool:
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AcousticBridgeNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print('[acoustic_bridge] KeyboardInterrupt received, shutting down.')
    finally:
        try:
            node.shutdown_bridge()
        finally:
            try:
                node.destroy_node()
            except Exception:
                pass

            try:
                if rclpy.ok():
                    rclpy.shutdown()
            except Exception:
                pass