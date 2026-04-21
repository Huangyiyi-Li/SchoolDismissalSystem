import unittest

from src.services.udp_parser import parse_udp_packet


class UDPParserTests(unittest.TestCase):
    def test_valid_packet_parses_sequence_and_card(self):
        packet = bytearray(22)
        packet[0] = 0xC1
        packet[7] = 17
        packet[10:14] = (123456789).to_bytes(4, byteorder="little")

        parsed = parse_udp_packet(bytes(packet))

        self.assertEqual(parsed.sequence_id, 17)
        self.assertEqual(parsed.card_id, "123456789")

    def test_invalid_header_raises_value_error(self):
        packet = bytearray(22)
        packet[0] = 0x00

        with self.assertRaises(ValueError):
            parse_udp_packet(bytes(packet))


if __name__ == "__main__":
    unittest.main()

