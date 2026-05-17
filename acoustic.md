# 项目说明

本项目通过串口接收触发帧来控制音响播放声音。核心流程如下：

- 串口节点为 serial_driver_ros2 包中的 serial_cmd_sender，可通过 launch 启动。
- 节点持续轮询串口，当收到触发帧后调用 release_spear.sh 脚本。
- release_spear.sh 会播放 generated_wavs/fast_release_spear.wav。

关键文件路径：

- 串口节点源码: /home/r1/acoustic/src/serial_driver_ros2/src/serial_main.cpp
- 串口通信实现: /home/r1/acoustic/src/serial_driver_ros2/src/serial_driver.cpp
- 协议定义: /home/r1/acoustic/src/serial_driver_ros2/include/serial_driver/protocol_defs.hpp
- 启动文件: /home/r1/acoustic/src/serial_driver_ros2/launch/serial_driver.launch.py
- 配置文件: /home/r1/acoustic/src/serial_driver_ros2/config/serial_config.yaml
- 音响脚本: /home/r1/acoustic/src/acoustic_comm/scripts/release_spear.sh

注意事项：

- 串口设备通常是 /dev/ttyUSB0，确保没有其它进程同时占用该串口。
- 如果另一个 CMD4 也打开 /dev/ttyUSB0，会导致串口冲突，需要停掉 CMD4 或更换端口。

启动命令示例：

source /home/r1/acoustic/install/setup.bash && ros2 launch serial_driver serial_driver.launch.py

# 串口通信协议说明

触发音响的帧格式：

- 帧头: 0xFF 0xFF
- 长度: 0x00
- 校验和: 所有前面字节求和后取低 8 位

触发帧示例：

FF FF 00 FE

校验计算：

0xFF + 0xFF + 0x00 = 0x1FE，取低 8 位为 0xFE。

接收逻辑说明：

- 节点会轮询串口数据流。
- 当检测到帧头 0xFF 0xFF、长度 0x00 且校验和匹配时，触发播放脚本。
- 每接收到一帧触发帧，都会执行一次 release_spear.sh。
