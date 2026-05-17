# 适用于机器人上/下位机串口通信的驱动（上位机部分）
> NOTE:此仓库基于Ubuntu22.04-ros-humble实现\
> 通信协议本身使用纯CPP实现，不局限于ROS等系统\
> 本仓库[主函数](src/serial_main.cpp)提供ROS2可用的[测试样例](#demo)，若使用ROS1或外部调用等场景需要自行修改launch文件或对应编译配置，使用ROS1可以参照[ros1版本仓库](https://github.com/CGC12123/serial_driver_ros1.git)

## Requirement
需要先安装 `serial` 库，在ubuntu22中无法直接使用apt安装，故需要从源码安装

```bash
git clone https://github.com/RoverRobotics-forks/serial-ros2.git
cd serial-ros2
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

## 通信协议
### 协议帧格式
| 字节索引 | 字段名     | 大小（字节） | 示例值          | 描述说明                                           |
|----------|------------|---------------|-----------------|----------------------------------------------------|
| 0        | 帧头1      | 1             | `0x0F`          | 固定帧头起始标志                                  |
| 1        | 帧头2      | 1             | `0xF0` / `0xFF` | `0xF0` 表示**发送帧**，`0xFF` 表示**接收帧**     |
| 2        | 数据长度   | 1             | `0x04`          | 后续数据字段长度（不包括帧头和校验和）            |
| 3～N     | 数据       | N（可变）     | `0x03, 0xE8 ...`| 以 2 字节为单位的 int16（缩放后 float 数据）    |
| N + 1    | 校验和     | 1             | `0x??`          | 对前面所有字节求和的低 8 位，用于验证完整性       |

### 数据说明
- 每 2 字节表示一个 `int16_t`，是浮点数 ×1000 后的整数形式。
- 数据数量 = 数据长度 ÷ 2。

### 数据demo
发送发送 float 数组 `{1.0f, -2.0f}`

| 字段名   | 十六进制示例                     | 说明                              |
|----------|----------------------------------|-----------------------------------|
| 帧头1    | `0x0F`                           | 固定值                            |
| 帧头2    | `0xF0`                           | 发送帧                            |
| 长度     | `0x04`                           | 两个 float，共 4 字节（2 x int16） |
| 数据     | `0x03, 0xE8, 0xF8, 0x30`         | `1000` → 1.0，`-2000` → -2.0      |
| 校验和   | `0x16`                           | 对前面所有字节求和取低 8 位       |

## Usage
### 串口及波特率设置
在[config/serial_config.yaml](config/serial_config.yaml)中设置
```
serial_cmd_sender:
  ros__parameters:
    port: "/dev/ttyS1"
    baudrate: 115200
```

### 函数调用
参照[include/serial_driver/serial_comm.hpp](include/serial_driver/serial_comm.hpp)
```
// init
SerialComm(const std::string& port, unsigned long baudrate);

// send
bool success = serial_comm_ptr->sendFloatArrayCommand(speeds);

// receive
std::vector<float> readFloatArrayResponse();
```

### demo
一个基于ros的示例如[src/serial_main.cpp](src/serial_main.cpp)，为订阅/LIVO2/pose_offset话题并通过串口发送数据
```
ros2 launch serial_driver serial_driver.launch.py
```
默认订阅全局定位里程计话题 `/aft_mapped_in_map`（`nav_msgs/msg/Odometry`），发送 `[x, y, yaw]` 到下位机，
这样重启后仍基于重定位后的 `map` 全局坐标，而不是每次从本地初始点开始累计。

参数在 [config/serial_config.yaml](config/serial_config.yaml) 中配置：
- `global_pose_topic`: 默认 `/aft_mapped_in_map`
- `enable_cmd_vel`: 是否同时透传 `/cmd_vel`

同时有一个模拟导航模块发送数据的python脚本用于测试
```
python script/send_demo.py
```
### 数据解析
基于你提供的代码 serial_driver.cpp 和日志输出，以下是数据从浮点数转换为十六进制 Raw 数据的详细逐位解析。

#### 核心转换逻辑
代码中的核心转换公式是：
```cpp
int16_t scaled = static_cast<int16_t>(val * 1000);
```
即：**数值乘以 1000，取整，转为 16 位有符号整数（补码表示），然后按大端序（高字节在前）拆分。**

---

#### 1. 数据转换详解

##### 第一个数：`-0.003451`
1.  **缩放**：`-0.003451 * 1000 = -3.451`
2.  **取整**：`static_cast<int16_t>(-3.451)` 截断为 **`-3`**
3.  **转十六进制（补码）**：
    *   3 的二进制：`0000 0000 0000 0011`
    *   -3 的补码（取反加一）：`1111 1111 1111 1101` -> **`FF FD`**

##### 第二个数：`-0.001270`
1.  **缩放**：`-0.001270 * 1000 = -1.270`
2.  **取整**：截断为 **`-1`**
3.  **转十六进制（补码）**：
    *   -1 的补码：`1111 1111 1111 1111` -> **`FF FF`**

##### 第三个数：`-0.056025`
1.  **缩放**：`-0.056025 * 1000 = -56.025`
2.  **取整**：截断为 **`-56`**
3.  **转十六进制（补码）**：
    *   56 的十六进制是 `0x38` (`0000 0000 0011 1000`)
    *   -56 的补码（取反加一）：`1111 1111 1100 1000` -> **`FF C8`**

---

#### 2. 帧结构组装

根据 `encodeFloatArray` 函数，帧结构如下：

| 字节索引 | 含义 | 代码对应 | 值 (Hex) | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| 0 | **帧头 1** | `protocol::FRAME_HEAD` | **`0F`** | 固定帧头 |
| 1 | **帧头 2** | `protocol::FRAME_HEAD_SEND` | **`F0`** | 发送方向标识 |
| 2 | **数据长度** | `data.size()` | **`06`** | 3个float × 2字节 = 6字节 |
| 3 | **数据1 高位** | `scaled >> 8` | **`FF`** | -3 的高8位 |
| 4 | **数据1 低位** | `scaled & 0xFF` | **`FD`** | -3 的低8位 |
| 5 | **数据2 高位** | `scaled >> 8` | **`FF`** | -1 的高8位 |
| 6 | **数据2 低位** | `scaled & 0xFF` | **`FF`** | -1 的低8位 |
| 7 | **数据3 高位** | `scaled >> 8` | **`FF`** | -56 的高8位 |
| 8 | **数据3 低位** | `scaled & 0xFF` | **`C8`** | -56 的低8位 |
| 9 | **校验和** | `calcChecksum` | **`C6`** | 前面所有字节累加 |

---

#### 3. 校验和计算验证

代码逻辑是累加前面所有字节，取低 8 位 (`sum & 0xFF`)。

计算过程：
1.  `0F` + `F0` = `FF` (255)
2.  `FF` + `06` = `105` -> 取低位 `05`
3.  `05` + `FF` = `104` -> 取低位 `04`
4.  `04` + `FD` = `101` -> 取低位 `01`
5.  `01` + `FF` = `100` -> 取低位 `00`
6.  `00` + `FF` = `FF` (255)
7.  `FF` + `FF` = `1FE` -> 取低位 `FE`
8.  `FE` + `C8` = `1C6` -> 取低位 **`C6`**

