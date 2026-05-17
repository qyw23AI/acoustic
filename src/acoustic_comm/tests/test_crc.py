from acoustic_comm.protocol.crc import crc8_atm


def test_crc8_atm_empty():
    assert crc8_atm(b"") == 0x00


def test_crc8_atm_known_vector_123456789():
    # CRC-8/ATM standard check value
    assert crc8_atm(b"123456789") == 0xF4


def test_crc8_atm_two_byte_payload():
    # Matches the demo/reference logic: cmd=0x0D, seq=0x01 -> crc=0xEE
    assert crc8_atm(bytes([0x0D, 0x01])) == 0xEE


def test_crc8_atm_is_deterministic():
    data = bytes([0x8A, 0x01])
    assert crc8_atm(data) == crc8_atm(data)


def test_crc8_atm_changes_when_input_changes():
    a = bytes([0x8A, 0x01])
    b = bytes([0x8A, 0x02])
    assert crc8_atm(a) != crc8_atm(b)