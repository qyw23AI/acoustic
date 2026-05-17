# src/acoustic_comm/protocol/crc.py

def crc8_atm(data_bytes: bytes) -> int:
    """
    CRC-8/ATM
      poly   = 0x07
      init   = 0x00
      xorout = 0x00
    """
    crc = 0x00
    for b in data_bytes:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) & 0xFF) ^ 0x07
            else:
                crc = (crc << 1) & 0xFF
    return crc