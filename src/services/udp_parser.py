from __future__ import annotations

from dataclasses import dataclass

PACKET_LENGTH = 22
PACKET_HEADER = 0xC1


@dataclass(frozen=True)
class ParsedPacket:
    sequence_id: int
    card_id: str


def parse_udp_packet(data: bytes) -> ParsedPacket:
    if len(data) != PACKET_LENGTH:
        raise ValueError(f"invalid packet length: {len(data)}")
    if data[0] != PACKET_HEADER:
        raise ValueError(f"invalid header: {data[0]:02X}")

    sequence_id = data[7]
    card_id = str(int.from_bytes(data[10:14], byteorder="little"))
    return ParsedPacket(sequence_id=sequence_id, card_id=card_id)


def extract_tcp_packets(buffer: bytes | bytearray) -> tuple[list[bytes], bytearray]:
    pending = bytearray(buffer)
    packets: list[bytes] = []

    while True:
        if len(pending) < PACKET_LENGTH:
            break

        if pending[0] != PACKET_HEADER:
            header_index = pending.find(bytes([PACKET_HEADER]), 1)
            if header_index == -1:
                pending = pending[-(PACKET_LENGTH - 1):]
                break
            del pending[:header_index]
            continue

        packets.append(bytes(pending[:PACKET_LENGTH]))
        del pending[:PACKET_LENGTH]

    return packets, pending


def extract_ascii_card_lines(buffer: bytes | bytearray) -> tuple[list[str], bytearray]:
    pending = bytearray(buffer)
    card_ids: list[str] = []

    while True:
        newline_index = pending.find(b"\n")
        if newline_index == -1:
            break

        raw_line = bytes(pending[: newline_index + 1])
        del pending[: newline_index + 1]

        line = raw_line.strip()
        if not line:
            continue

        try:
            decoded = line.decode("ascii")
        except UnicodeDecodeError:
            continue

        if decoded.isdigit():
            card_ids.append(decoded)

    return card_ids, pending
