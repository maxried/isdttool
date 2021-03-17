# coding=utf-8

"""Well, these are unit tests."""

import unittest
from typing import List

# noinspection PyProtectedMember
from isdttool import set_debug
from .charger.charger import Charger, __generate_raw_frames__, __escape_synchronization__, \
    __unescape_synchronization__
from .charger.representation import parse_packet


class MyTestCase(unittest.TestCase):
    """These are test cases for protocol decoding."""

    def setUp(self) -> None:
        """Enable verbose protocol debugging during setup."""
        set_debug(True)

    def test_a4_version(self) -> None:
        """Test if the response of a version request of an A4 charger can be parsed."""
        charger: Charger = Charger(None)
        payload: List[bytearray] = [bytearray(b'\x02\x2d\xaa\x21\x27\xe1\x41\x34\x00\x00\x00\x00'
                                              b'\x00\x00\x01\x02\x00\x00\x01\x00\x00\x01\x01\x00'
                                              b'\x00\x11\x41\x34\x00\x00\x00\x00\x00\x00\x00\x00'
                                              b'\x00\x00\x12\x08\x1d\x11\x15\x3b\xc2\x00\x00\x00'
                                              b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                                              b'\x00\x00\x00\x00')]
        self.assertIsNotNone(parse_packet(charger.read_packet(payload)))

    def test_real_world_metrics_response(self) -> None:
        """Test if a metrics packet can be read, and parsed."""
        charger: Charger = Charger(None)
        print('Testing captured frame')
        payload: List[bytearray] = [
            bytearray(b'\x02 \xaa!\x1a\xdf\x00\x04\x07\x01")d\x00\x00\x00\x009\x00\x00\x00`\x02'
                      b'\xf0\x00\x00\x00\xc0\x01\x00\x00!\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                      b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                      b'\x00\x00\x00\x00')]
        self.assertIsNotNone(parse_packet(charger.read_packet(payload)))

    def test_protocol_decode_long(self) -> None:
        """Pack, and unpack a long payload, test if they are equal."""
        charger: Charger = Charger(None)

        print('Testing long frame')
        payload = bytearray(b'0123456789' * 7)
        original = __generate_raw_frames__(payload=payload)
        decoded_payload = charger.read_packet(original)
        self.assertEqual(payload, decoded_payload)

    def test_protocol_decode_small(self) -> None:
        """Pack, and unpack a short payload, test if they are equal."""
        charger: Charger = Charger(None)

        print('Testing small frame')
        payload = bytearray(b'0123456789')
        original = __generate_raw_frames__(payload=payload)
        decoded_payload = charger.read_packet(original)
        self.assertEqual(payload, decoded_payload)

    def test_escaping(self) -> None:
        """Escape, and unescape a payload, test if they are equal."""
        print('Testing escaping, and un-escaping the payload')
        payload = bytearray()
        for i in range(0, 255):
            payload.append(i)
        self.assertEqual(__unescape_synchronization__(__escape_synchronization__(payload)),
                         payload)

    def test_broken_sync(self) -> None:
        """Test a packet with broken synchronisation."""
        print('Testing broken sync')
        payload = bytearray(b'\x01\x02\xAA\xAA\xAA\x01')
        self.assertEqual(len(__unescape_synchronization__(payload)), 4)

    # def test_real_life_aa(self) -> None:
    #     payload = bytearray(b'\x21\x1a\xdf\x01\x0b\x05\x01\x22\x2b\x63\x76\x07\x97\x02'
    #                         b'\x1e\x00\xf2\x04\xba\x07\xaa\xaa\x02\x00\x00\x79\x08\x00'
    #                         b'\x00\xf4\xaa\x00')
    #
    #     __unescape_synchronization__(payload)

    def test_write_block1(self) -> None:
        """
        Test a multi frame packet captured during firmware update, verify against firmware.

        Test 1/4
        """
        print('Testing larger packet captured from the official firmware updater')
        capture: List[bytearray] = [
            bytearray(b'\x01\x3E\xAA\x12\x86\xF4\x00\x00\x40\x00\x08\x90\x1C\x00\x20\x49\x90\x03'
                      b'\x08\x29\x8E\x03\x08\x2B\x8E\x03\x08\x2D\x8E\x03\x08\x2F\x8E\x03\x08\x31'
                      b'\x8E\x03\x08\x0C\x8E\x03\x08\x0C\x8E\x03\x08\x0C\x8E\x03\x08\x0C\x8E\x03'
                      b'\x08\x5B\xCC\x01\x08\x33\x8E\x03\x08\x00'),
            bytearray(b'\x01\x3E\x00\x00\x00\x15\xCC\x01\x08\x45\x6A\x01\x08\xDD\x74\x03\x08\xE1'
                      b'\x74\x03\x08\xE5\x74\x03\x08\xE9\x74\x03\x08\xED\x74\x03\x08\xF1\x74\x03'
                      b'\x08\xF5\x74\x03\x08\xF9\x74\x03\x08\xFD\x74\x03\x08\x01\x75\x03\x08\x05'
                      b'\x75\x03\x08\x97\x78\x01\x08\x09\x75\x03'),
            bytearray(b'\x01\x0E\x08\x0D\x75\x03\x08\x11\x75\x03\x08\x15\x75\x03\x08\xBA')]

        charger: Charger = Charger(None)
        read_payload = charger.read_packet(capture)
        self.assertEqual(len(read_payload), 0x86)
        self.assertEqual(read_payload,
                         bytearray(b'\xF4\x00\x00\x40\x00\x08\x90\x1C\x00\x20\x49\x90\x03\x08'
                                   b'\x29\x8E\x03\x08\x2B\x8E\x03\x08\x2D\x8E\x03\x08\x2F\x8E'
                                   b'\x03\x08\x31\x8E\x03\x08\x0C\x8E\x03\x08\x0C\x8E\x03\x08'
                                   b'\x0C\x8E\x03\x08\x0C\x8E\x03\x08\x5B\xCC\x01\x08\x33\x8E'
                                   b'\x03\x08\x00\x00\x00\x00\x15\xCC\x01\x08\x45\x6A\x01\x08'
                                   b'\xDD\x74\x03\x08\xE1\x74\x03\x08\xE5\x74\x03\x08\xE9\x74'
                                   b'\x03\x08\xED\x74\x03\x08\xF1\x74\x03\x08\xF5\x74\x03\x08'
                                   b'\xF9\x74\x03\x08\xFD\x74\x03\x08\x01\x75\x03\x08\x05\x75'
                                   b'\x03\x08\x97\x78\x01\x08\x09\x75\x03\x08\x0D\x75\x03\x08'
                                   b'\x11\x75\x03\x08\x15\x75\x03\x08'))

    def test_write_block2(self) -> None:
        """
        Test a multi frame packet captured during firmware update, verify against firmware.

        Test 2/4
        """
        print('Testing larger packet captured from the official firmware updater 2')
        charger: Charger = Charger(None)
        capture: List[bytearray] = [
            bytearray(b'\x01\x3e\xaa\x12\x86\xf4\x00\x80\x42\x00\x08\x00\x7d\xfa\x10\x00\x00\x07'
                      b'\xf7\x5d\xb0\x00\x00\x0d\x90\x07\xf0\x00\x00\x0f\x70\x08\xd0\x00\x00\x0c'
                      b'\xa0\x6f\x60\x00\x00\x07\xf9\xf6\x00\x00\x00\x04\xff\x40\x00\x06\x70\x1d'
                      b'\xee\x60\x00\x0e\x90\x7f\x35\xf3\x00\x6f'),
            bytearray(b'\x01\x3e\x40\xca\x00\x9e\x30\xdb\x00\xf7\x00\x1c\xfb\xf3\x00\xbd\x00\x01'
                      b'\xef\xc1\x00\x5f\xb5\x5b\xf9\xfe\x81\x05\xbf\xd9\x40\x28\xb0\xfb\xfb\xeb'
                      b'\xb8\xb7\x54\x00\x00\x00\x10\x00\x99\x02\xf4\x09\xb0\x1f\x60\x5f\x10\x8c'
                      b'\x00\xba\x00\xe7\x00\xf7\x00\xf7\x00\xf7'),
            bytearray(b'\x01\x0e\x00\xd7\x00\xbb\x00\x7d\x00\x4f\x20\x0e\x70\x07\xd0\xa9')]

        read_payload = charger.read_packet(capture)
        self.assertEqual(read_payload,
                         bytearray(b'\xf4\x00\x80\x42\x00\x08\x00\x7D\xFA\x10\x00\x00\x07\xF7'
                                   b'\x5D\xB0\x00\x00\x0D\x90\x07\xF0\x00\x00\x0F\x70\x08\xD0'
                                   b'\x00\x00\x0C\xA0\x6F\x60\x00\x00\x07\xF9\xF6\x00\x00\x00'
                                   b'\x04\xFF\x40\x00\x06\x70\x1D\xEE\x60\x00\x0E\x90\x7F\x35'
                                   b'\xF3\x00\x6F\x40\xCA\x00\x9E\x30\xDB\x00\xF7\x00\x1C\xFB'
                                   b'\xF3\x00\xBD\x00\x01\xEF\xC1\x00\x5F\xB5\x5B\xF9\xFE\x81'
                                   b'\x05\xBF\xD9\x40\x28\xB0\xFB\xFB\xEB\xB8\xB7\x54\x00\x00'
                                   b'\x00\x10\x00\x99\x02\xF4\x09\xB0\x1F\x60\x5F\x10\x8C\x00'
                                   b'\xBA\x00\xE7\x00\xF7\x00\xF7\x00\xF7\x00\xD7\x00\xBB\x00'
                                   b'\x7D\x00\x4F\x20\x0E\x70\x07\xD0'))

    def test_write_block_aa(self) -> None:
        """
        Test a multi frame packet captured during firmware update, verify against firmware.

        This one is special because it also has 0xAA in the payload.
        Test 3/4
        """
        print('Testing large packet captured with 0xAA in payload.')
        charger: Charger = Charger(None)
        capture: List[bytearray] = [
            bytearray(b'\x01\x3e\xaa\x12\x86\xf4\x00\x00\x43\x00\x08\x01\xe5\x00\x77\x01\x00\x00'
                      b'\x3e\x10\x00\x0b\x80\x00\x05\xf1\x00\x00\xe7\x00\x00\x9b\x00\x00\x7f\x00'
                      b'\x00\x4f\x40\x00\x1f\x40\x00\x0f\x70\x00\x0f\x70\x00\x0f\x70\x00\x2f\x40'
                      b'\x00\x4f\x30\x00\x7e\x00\x00\xaa\xaa\x00'),
            bytearray(b'\x01\x3e\x01\xf6\x00\x06\xe0\x00\x0d\x70\x00\x4b\x00\x00\x00\x4f\x00\x00'
                      b'\x20\x4f\x01\x10\x9f\xcf\xcf\x60\x04\xef\xc2\x00\x04\xfb\xe2\x00\x0b\x70'
                      b'\x97\x00\x01\x00\x10\x00\x00\x00\x7f\x00\x00\x00\x00\x7f\x00\x00\x00\x00'
                      b'\x7f\x00\x00\x00\x00\x7f\x00\x00\x4f\xff'),
            bytearray(b'\x01\x0f\xff\xff\xfb\x14\x44\x9f\x44\x43\x00\x00\x7f\x00\x00\x00\x90')]

        read_payload = charger.read_packet(capture)
        self.assertEqual(read_payload,
                         bytearray(b'\xf4\x00\x00\x43\x00\x08\x01\xe5\x00\x77\x01\x00\x00\x3e'
                                   b'\x10\x00\x0b\x80\x00\x05\xf1\x00\x00\xe7\x00\x00\x9b\x00'
                                   b'\x00\x7f\x00\x00\x4f\x40\x00\x1f\x40\x00\x0f\x70\x00\x0f'
                                   b'\x70\x00\x0f\x70\x00\x2f\x40\x00\x4f\x30\x00\x7e\x00\x00'
                                   b'\xaa\x00\x01\xf6\x00\x06\xe0\x00\x0d\x70\x00\x4b\x00\x00'
                                   b'\x00\x4f\x00\x00\x20\x4f\x01\x10\x9f\xcf\xcf\x60\x04\xef'
                                   b'\xc2\x00\x04\xfb\xe2\x00\x0b\x70\x97\x00\x01\x00\x10\x00'
                                   b'\x00\x00\x7f\x00\x00\x00\x00\x7f\x00\x00\x00\x00\x7f\x00'
                                   b'\x00\x00\x00\x7f\x00\x00\x4f\xff\xff\xff\xfb\x14\x44\x9f'
                                   b'\x44\x43\x00\x00\x7f\x00\x00\x00'))

    def test_large_packet_for_firmware_writing(self) -> None:
        """
        Generate multi frame firmware update packets, and test them against what the updater does.

        Test 4/4
        """
        print('Test the creation of real world update packets')
        payload_in: bytearray = bytearray(b'\xf4\x00\x00\x43\x00\x08\x01\xe5\x00\x77\x01\x00\x00'
                                          b'\x3e\x10\x00\x0b\x80\x00\x05\xf1\x00\x00\xe7\x00\x00'
                                          b'\x9b\x00\x00\x7f\x00\x00\x4f\x40\x00\x1f\x40\x00\x0f'
                                          b'\x70\x00\x0f\x70\x00\x0f\x70\x00\x2f\x40\x00\x4f\x30'
                                          b'\x00\x7e\x00\x00\xaa\x00\x01\xf6\x00\x06\xe0\x00\x0d'
                                          b'\x70\x00\x4b\x00\x00\x00\x4f\x00\x00\x20\x4f\x01\x10'
                                          b'\x9f\xcf\xcf\x60\x04\xef\xc2\x00\x04\xfb\xe2\x00\x0b'
                                          b'\x70\x97\x00\x01\x00\x10\x00\x00\x00\x7f\x00\x00\x00'
                                          b'\x00\x7f\x00\x00\x00\x00\x7f\x00\x00\x00\x00\x7f\x00'
                                          b'\x00\x4f\xff\xff\xff\xfb\x14\x44\x9f\x44\x43\x00\x00'
                                          b'\x7f\x00\x00\x00')

        generated_frames = __generate_raw_frames__(payload_in)
        charger: Charger = Charger(None)
        payload_out = charger.read_packet(generated_frames.copy())

        self.assertEqual(payload_in, payload_out)
        self.assertEqual(generated_frames,
                         [bytearray(b'\x01\x3e\xaa\x12\x86\xf4\x00\x00\x43\x00\x08\x01\xe5\x00'
                                    b'\x77\x01\x00\x00\x3e\x10\x00\x0b\x80\x00\x05\xf1\x00\x00'
                                    b'\xe7\x00\x00\x9b\x00\x00\x7f\x00\x00\x4f\x40\x00\x1f\x40'
                                    b'\x00\x0f\x70\x00\x0f\x70\x00\x0f\x70\x00\x2f\x40\x00\x4f'
                                    b'\x30\x00\x7e\x00\x00\xaa\xaa\x00'),
                          bytearray(b'\x01\x3e\x01\xf6\x00\x06\xe0\x00\x0d\x70\x00\x4b\x00\x00'
                                    b'\x00\x4f\x00\x00\x20\x4f\x01\x10\x9f\xcf\xcf\x60\x04\xef'
                                    b'\xc2\x00\x04\xfb\xe2\x00\x0b\x70\x97\x00\x01\x00\x10\x00'
                                    b'\x00\x00\x7f\x00\x00\x00\x00\x7f\x00\x00\x00\x00\x7f\x00'
                                    b'\x00\x00\x00\x7f\x00\x00\x4f\xff'),
                          bytearray(b'\x01\x0f\xff\xff\xfb\x14\x44\x9f\x44\x43\x00\x00\x7f\x00\x00'
                                    b'\x00\x90')])


if __name__ == '__main__':
    unittest.main()
