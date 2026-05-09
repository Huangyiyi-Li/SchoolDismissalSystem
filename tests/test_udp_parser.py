import unittest

from src.services.udp_parser import (
    extract_ascii_card_lines,
    extract_ascii_card_payloads,
    extract_tcp_packets,
    parse_udp_packet,
)


class UDPParserTests(unittest.TestCase):
    def _make_packet(self, sequence_id=17, card_id=123456789):
        packet = bytearray(22)
        packet[0] = 0xC1
        packet[7] = sequence_id
        packet[10:14] = int(card_id).to_bytes(4, byteorder="little")
        return bytes(packet)

    def test_valid_packet_parses_sequence_and_card(self):
        packet = self._make_packet()

        parsed = parse_udp_packet(packet)

        self.assertEqual(parsed.sequence_id, 17)
        self.assertEqual(parsed.card_id, "123456789")

    def test_invalid_header_raises_value_error(self):
        packet = bytearray(22)
        packet[0] = 0x00

        with self.assertRaises(ValueError):
            parse_udp_packet(bytes(packet))

    def test_invalid_length_raises_value_error(self):
        packet = bytearray(21)
        packet[0] = 0xC1

        with self.assertRaises(ValueError):
            parse_udp_packet(bytes(packet))

    def test_extract_tcp_packets_splits_multiple_frames(self):
        packet1 = self._make_packet(sequence_id=1, card_id=111)
        packet2 = self._make_packet(sequence_id=2, card_id=222)

        packets, pending = extract_tcp_packets(packet1 + packet2)

        self.assertEqual(packets, [packet1, packet2])
        self.assertEqual(bytes(pending), b"")

    def test_extract_tcp_packets_keeps_partial_tail(self):
        packet = self._make_packet(sequence_id=3, card_id=333)

        packets, pending = extract_tcp_packets(packet + packet[:8])

        self.assertEqual(packets, [packet])
        self.assertEqual(bytes(pending), packet[:8])

    def test_extract_tcp_packets_resyncs_after_noise(self):
        packet = self._make_packet(sequence_id=4, card_id=444)

        packets, pending = extract_tcp_packets(b"\x00\x01\x02" + packet)

        self.assertEqual(packets, [packet])
        self.assertEqual(bytes(pending), b"")

    def test_extract_ascii_card_lines_reads_crlf_delimited_card_ids(self):
        card_ids, pending = extract_ascii_card_lines(b"3655451601\r\n9876543210\r\n")

        self.assertEqual(card_ids, ["3655451601", "9876543210"])
        self.assertEqual(bytes(pending), b"")

    def test_extract_ascii_card_lines_keeps_partial_line(self):
        card_ids, pending = extract_ascii_card_lines(b"3655451601\r\n12345")

        self.assertEqual(card_ids, ["3655451601"])
        self.assertEqual(bytes(pending), b"12345")

    def test_extract_tcp_packets_does_not_truncate_ascii_card_streams(self):
        buffer = b"3651603617\r\n3651603617\r\n"

        packets, pending = extract_tcp_packets(buffer)
        card_ids, remainder = extract_ascii_card_lines(pending)

        self.assertEqual(packets, [])
        self.assertEqual(card_ids, ["3651603617", "3651603617"])
        self.assertEqual(bytes(remainder), b"")

    def test_extract_ascii_card_payloads_reads_udp_ascii_card_id(self):
        card_ids = extract_ascii_card_payloads(b"3655451601\r\n")

        self.assertEqual(card_ids, ["3655451601"])

    def test_extract_ascii_card_payloads_accepts_bare_ascii_card_id(self):
        card_ids = extract_ascii_card_payloads(b"3655451601")

        self.assertEqual(card_ids, ["3655451601"])

    def test_extract_ascii_card_payloads_ignores_non_ascii_payload(self):
        card_ids = extract_ascii_card_payloads(b"\xc1\x00\x01\x02")

        self.assertEqual(card_ids, [])


if __name__ == "__main__":
    unittest.main()
