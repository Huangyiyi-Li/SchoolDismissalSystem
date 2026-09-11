import tempfile
from pathlib import Path
import pytest
from src.services.readers.uhf_protocol import crc16, parse_frame, StreamParser, encode_epc
from src.database import DatabaseManager

EPC = '3005FB63AC1F3841EC880467'

def test_vendor_crc_vector():
    assert crc16(bytes.fromhex('040001DB4B')) == 0

def test_epc_preserves_order_and_leading_zero():
    assert parse_frame(encode_epc('0000' + EPC)) == '0000' + EPC

@pytest.mark.parametrize('mutation', ['crc', 'length', 'status', 'command', 'empty'])
def test_reject_invalid_frames(mutation):
    data = bytearray(encode_epc(EPC))
    if mutation == 'crc': data[-1] ^= 1
    elif mutation == 'length': data[0] -= 1
    elif mutation in ('status', 'command'):
        data[3 if mutation == 'status' else 2] = 1
        data[-2:] = crc16(data[:-2]).to_bytes(2, 'little')
    else:
        data = bytearray.fromhex('0500EE00'); data += crc16(data).to_bytes(2,'little')
    assert parse_frame(data) is None

def test_split_coalesced_and_noise():
    frame = encode_epc(EPC)
    parser = StreamParser()
    assert parser.feed(frame[:7]) == []
    assert parser.feed(frame[7:] + frame) == [frame, frame]
    assert parser.feed(b'\xff\x00\x01' + frame) == [frame]
    bad = bytearray(frame); bad[-1] ^= 1
    assert parser.feed(bad + frame) == [frame]
    parser.feed(b'\xff' * 10000)
    assert len(parser.buffer) <= 256

def test_binding_survives_sync_and_checks_school_and_card():
    with tempfile.TemporaryDirectory() as directory:
        db = DatabaseManager(str(Path(directory) / 'school.db'))
        db.add_mapping('123', '一班', 'c1', 's1', 1)
        db.bind_credential('s1', EPC, '123')
        assert db.resolve_credential('s1', EPC) == '123'
        assert db.resolve_credential('s2', EPC) is None
        db.clear_mappings()
        assert len(db.list_credentials('s1')) == 1
        assert db.resolve_credential('s1', EPC) is None
        db.add_mapping('123', '一班', 'c1', 's1', 1)
        assert db.resolve_credential('s1', EPC) == '123'
        db.delete_mapping('123')
        db.add_mapping('123', '二班', 'c2', 's1', 1)
        assert db.resolve_credential('s1', EPC) is None

def test_real_four_byte_frame_matches_school_decimal_card(tmp_path):
    frame = bytes.fromhex('09 00 EE 00 AE 1D AF 0B 4F 8F')
    assert crc16(frame) == 0
    assert parse_frame(frame) == 'AE1DAF0B'
    db = DatabaseManager(str(tmp_path / 'school.db'))
    db.add_mapping('2921180939', '一班', 'c1', 's1', 1)
    assert db.resolve_credential('s1', parse_frame(frame)) == '2921180939'
    assert db.resolve_credential('s2', parse_frame(frame)) is None
    assert db.resolve_credential('s1', '0000AE1DAF0B') is None


def test_explicit_binding_precedes_decimal_and_stale_binding_blocks_fallback(tmp_path):
    db = DatabaseManager(str(tmp_path / 'school.db'))
    db.add_mapping('2921180939', '一班', 'c1', 's1', 1)
    db.add_mapping('123', '二班', 'c2', 's1', 1)
    db.bind_credential('s1', 'AE1DAF0B', '123')
    assert db.resolve_credential('s1', 'AE1DAF0B') == '123'
    db.delete_mapping('123')
    assert db.resolve_credential('s1', 'AE1DAF0B') is None
