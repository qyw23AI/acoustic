#ifndef SERIAL_COMM_HPP
#define SERIAL_COMM_HPP

#include <string>
#include <vector>
#include <cstdint>
#include <cstddef>
#include <serial/serial.h>

class SerialComm {
public:
    SerialComm(const std::string& port, unsigned long baudrate);
    ~SerialComm();

    // send
    bool sendFloatArrayCommand(const std::vector<float>& values);
    // receive
    std::vector<float> readFloatArrayResponse();
    // trigger frame receive
    size_t readTriggerFrames();


private:
    serial::Serial serial_port_;

    bool isOpen();
    std::vector<uint8_t> encodeFloatArray(const std::vector<float>& values);
};

#endif
