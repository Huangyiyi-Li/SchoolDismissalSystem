from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedPacket:
    sequence_id: int
    card_id: str


def parse_udp_packet(data: bytes) -> ParsedPacket:
    if len(data) != 22:
        raise ValueError(f"invalid packet length: {len(data)}")
    if data[0] != 0xC1:
        raise ValueError(f"invalid header: {data[0]:02X}")

    sequence_id = data[7]
    card_id = str(int.from_bytes(data[10:14], byteorder="little"))
    return ParsedPacket(sequence_id=sequence_id, card_id=card_id)

