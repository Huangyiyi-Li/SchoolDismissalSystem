"""uhfreader18 v2.0A §8.4.9: 6C inventory active output only.

The device must be configured for 6C and Mem_Inven 04/05. Other memory
modes use the same EE header and cannot be distinguished from this frame.
"""
import re


def crc16(data):
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x8408 if value & 1 else 0)
    return value


def normalize_epc(value):
    value = ''.join(str(value).split()).upper()
    if not re.fullmatch(r'[0-9A-F]+', value) or len(value) % 4 or not 4 <= len(value) <= 500:
        raise ValueError('标签编号应为完整的十六进制字，长度为 4 的倍数')
    return value


def encode_epc(epc):
    payload = bytes.fromhex(normalize_epc(epc))
    data = bytes([len(payload) + 5, 0, 0xEE, 0]) + payload
    return data + crc16(data).to_bytes(2, 'little')


def parse_frame(frame):
    if len(frame) < 8 or len(frame) != frame[0] + 1:
        return None
    if frame[2:4] != b'\xee\x00' or crc16(frame) != 0:
        return None
    payload = frame[4:-2]
    if len(payload) % 2:
        return None
    return payload.hex().upper()


class StreamParser:
    """One instance per TCP connection. Recover at a complete CRC-valid frame."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, incoming):
        self.buffer.extend(incoming)
        frames = []
        while self.buffer:
            found = False
            for offset in range(len(self.buffer)):
                total = self.buffer[offset] + 1
                if total < 8 or total > 256 or total % 2:
                    continue
                if offset + total > len(self.buffer):
                    continue
                candidate = bytes(self.buffer[offset:offset + total])
                if parse_frame(candidate) is not None:
                    frames.append(candidate)
                    del self.buffer[:offset + total]
                    found = True
                    break
            if not found:
                # Any possible incomplete frame fits in the final 255 bytes.
                if len(self.buffer) > 255:
                    del self.buffer[:-255]
                break
        return frames
