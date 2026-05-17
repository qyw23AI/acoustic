#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "serial_driver/serial_comm.hpp"
#include <cmath>
#include <cstdlib>
#include <thread>
#include <fstream>

using std::placeholders::_1;

class SerialCmdSender : public rclcpp::Node
{
public:
    SerialCmdSender() : Node("serial_cmd_sender")
    {
        // 声明参数
        this->declare_parameter<std::string>("port", "/dev/ttyACM1");
        this->declare_parameter<int>("baudrate", 115200);
        this->declare_parameter<bool>("enable_cmd_vel", false);
        this->declare_parameter<std::string>("cmd_vel_topic", "/cmd_vel");
        this->declare_parameter<std::string>("global_pose_topic", "/aft_mapped_in_map");
        this->declare_parameter<std::string>(
            "release_script",
            "/home/r1/acoustic/src/acoustic_comm/scripts/release_spear.sh");

        // 获取参数
        std::string port = this->get_parameter("port").as_string();
        int baudrate = this->get_parameter("baudrate").as_int();
        const bool enable_cmd_vel = this->get_parameter("enable_cmd_vel").as_bool();
        const std::string cmd_vel_topic = this->get_parameter("cmd_vel_topic").as_string();
        const std::string global_pose_topic = this->get_parameter("global_pose_topic").as_string();
        release_script_ = this->get_parameter("release_script").as_string();

        // 初始化串口通信类
        comm_ = std::make_unique<SerialComm>(port, baudrate);

        if (enable_cmd_vel)
        {
            sub_cmd_vel_ = this->create_subscription<geometry_msgs::msg::Twist>(
                cmd_vel_topic, 10, std::bind(&SerialCmdSender::cmdVelCallback, this, _1));
            RCLCPP_INFO(this->get_logger(), "cmd_vel enabled, subscribe: %s", cmd_vel_topic.c_str());
        }

        sub_global_odom_ = this->create_subscription<nav_msgs::msg::Odometry>(
            global_pose_topic, 50, std::bind(&SerialCmdSender::globalOdomCallback, this, _1));
        RCLCPP_INFO(this->get_logger(), "global pose subscribe: %s", global_pose_topic.c_str());

        if (!fileExists(release_script_)) {
            RCLCPP_WARN(this->get_logger(), "release_script not found: %s", release_script_.c_str());
        }

        trigger_timer_ = this->create_wall_timer(
            std::chrono::milliseconds(50),
            std::bind(&SerialCmdSender::pollTriggerFrames, this));
    }

private:
    // 从四元数计算偏航角（Z 轴），返回弧度
    static float quatToYaw(const geometry_msgs::msg::Quaternion &q)
    {
        // yaw (Z) = atan2(2(w*z + x*y), 1 - 2(y*y + z*z))
        const double siny_cosp = 2.0 * (q.w * q.z + q.x * q.y);
        const double cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
        return static_cast<float>(std::atan2(siny_cosp, cosy_cosp));
    }

    void cmdVelCallback(const geometry_msgs::msg::Twist::SharedPtr msg)
    {
        float vx = msg->linear.x;
        float wz = msg->angular.z;

        std::vector<float> speeds = {vx, wz};
        bool success = comm_->sendFloatArrayCommand(speeds);
        RCLCPP_INFO(this->get_logger(), "recv /cmd_vel -> [vx=%.4f, wz=%.4f], send=%s", vx, wz, success ? "OK" : "FAIL");
        if (!success)
        {
            RCLCPP_WARN(this->get_logger(), "Send Error");
        }
    }

    void globalOdomCallback(const nav_msgs::msg::Odometry::SharedPtr msg)
    {
        const float x = static_cast<float>(msg->pose.pose.position.x);
        const float y = static_cast<float>(msg->pose.pose.position.y);
        const float yaw = quatToYaw(msg->pose.pose.orientation);

        std::vector<float> payload = {x, y, yaw};
        const bool ok = comm_->sendFloatArrayCommand(payload);
        RCLCPP_INFO(this->get_logger(), "recv global odom -> [x=%.4f, y=%.4f, yaw=%.4f], send=%s", x, y, yaw, ok ? "OK" : "FAIL");
        if (!ok)
        {
            RCLCPP_WARN(this->get_logger(), "Send Error (global odom)");
        }
    }

    static bool fileExists(const std::string &path)
    {
        std::ifstream f(path);
        return f.good();
    }

    void pollTriggerFrames()
    {
        const size_t count = comm_->readTriggerFrames();
        if (count == 0) return;

        for (size_t i = 0; i < count; ++i) {
            triggerSoundAsync();
        }
    }

    void triggerSoundAsync()
    {
        const std::string script = release_script_;
        std::thread([this, script]() {
            const std::string cmd = "bash " + script;
            int ret = std::system(cmd.c_str());
            if (ret != 0) {
                RCLCPP_WARN(this->get_logger(), "release_script failed with code %d", ret);
            }
        }).detach();
    }

    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr sub_cmd_vel_;
    rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr sub_global_odom_;
    std::unique_ptr<SerialComm> comm_;
    rclcpp::TimerBase::SharedPtr trigger_timer_;
    std::string release_script_;
};

int main(int argc, char *argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<SerialCmdSender>());
    rclcpp::shutdown();
    return 0;
}
