# coding=utf-8

"""The USB framing of ISDT chargers.

Over USB, a packet travels in 64-byte HID reports. The packet is wrapped like this:

* 0x12 (computer to charger) or 0x21 (charger to computer), the payload length, the
  payload, and a checksum: the sum of all these bytes, modulo 256,
* every 0xAA in that is doubled, and a single 0xAA is put in front for synchronization,
* the result is cut into chunks of at most 62 bytes. Each chunk becomes one report: 0x01
  (request) or 0x02 (response), the chunk length, and the chunk, padded with zeros.

Other links, like Bluetooth LE, carry the same kind of packets without this framing. That is
why only UsbTransport uses it.
"""
import sys
from typing import Callable, List, Optional

import isdttool


def debug_log(*args, **kwargs) -> None:
    """
    Wrapper around print that prints to stderr, and is silenced if debug_mode is not True.
    :param args: positional args for print
    :param kwargs: keyword args for print
    """
    if isdttool.DEBUG_MODE:
        kwargs['file'] = sys.stderr
        print(*args, **kwargs)


def __escape_synchronization__(payload: bytearray) -> bytearray:
    """
    Duplicates all occurrences of 0xAA
    :param payload: Input
    :return: a new bytearray
    """
    result = bytearray()
    for b in payload:
        if b == 0xAA:
            result.append(0xAA)
        result.append(b)

    return result


def __unescape_synchronization__(payload: bytearray) -> bytearray:
    """
    Undoes the escape function. Drops erroneous 0xAA.
    :param payload: To un-escape
    :return: a new bytearray
    """
    sync_seen: bool = False
    result: bytearray = bytearray()
    for b in payload:
        if b == 0xAA:
            if sync_seen:
                result.append(0xAA)
            sync_seen = not sync_seen
        else:
            if sync_seen:
                debug_log('Protocol warning: Sync seen in mid-packet. '
                          'Discarding, but keeping the next character.')

            sync_seen = False
            result.append(b)

    return result


def __preprocess_payload__(data: bytearray) -> bytearray:
    """
    Escapes the payload, adds the length, the direction, and then escapes all
    synchronization symbols.
    :param data: The payload to construct the packet from. Must be <= 255 in length.
    :return: The preprocessed payload.
    """
    payload = bytearray()
    payload.append(0x12)  # Computer to charger
    payload.append(len(data) & 0xFF)
    payload.extend(data)

    checksum: int = 0
    for b in payload:
        checksum = (checksum + b) & 0xFF
    payload.append(checksum)

    payload = __escape_synchronization__(payload)
    payload.insert(0, 0xAA)

    return payload


def __generate_raw_frames__(payload: bytearray) -> List[bytearray]:
    """
    Generates the frames with with the correct chunk size, which contain the payload.
    Not really tested if it properly works with len(payload) > 60 which would end up in
    multiple frames.
    :param payload: The packet data.
    :return: A list of the frames to send.
    """
    preprocessed_payload = __preprocess_payload__(payload)
    split_payload = [preprocessed_payload[i:min(len(preprocessed_payload), i + 62)]
                     for i in range(0, len(preprocessed_payload), 62)]

    generated_frames: List[bytearray] = []

    for p in split_payload:
        this_frame = bytearray()
        this_frame.append(0x01)  # This is a request
        this_frame.append(len(p))
        this_frame.extend(p)

        generated_frames.append(this_frame)

    return generated_frames


def decode_frames(read_frame: Callable[[], bytes]) -> Optional[bytearray]:
    """
    Reassembles one packet from frames.
    :param read_frame: Returns the next frame, or an empty result when there is none.
    :return: The packet data. Reassembled, unescaped, and checked for errors. None if no frame
    arrived.
    """

    expected_packet_length: Optional[int] = None
    packet_data: Optional[bytearray] = None

    # We read 3 bytes more than we think we need, because the packet length as stated in the
    # packet does not contain the header of the packet, and its checksum.
    while expected_packet_length is None or len(packet_data) < expected_packet_length + 3:
        frame_as_received = bytearray(read_frame())
        debug_log('Reading', bytes(frame_as_received).hex())

        if len(frame_as_received) < 3:
            debug_log('Protocol error: Frame too short:', len(frame_as_received), 'bytes.',
                      'Returning already captured data.')
            return packet_data

        if frame_as_received[0] != 1 and frame_as_received[0] != 2:
            debug_log('Protocol warning: Neither request nor response: 0x{:02X}'
                      .format(frame_as_received[0]))

        frame_length = min(frame_as_received[1] + 2, len(frame_as_received))
        # This min is important. The charger sometimes has a different understanding about
        # how long a frame is. Sometimes it's the count of the remaining bytes after the
        # length field, sometimes it's the length of the entire frame. Always acting as if
        # the frame is two bytes longer as it's stated covers both options, and limiting it
        # to the total length of the actually received frame ensures we don't read out of
        # bounds.

        frame_body = frame_as_received[2:frame_length]

        if expected_packet_length is None:
            if frame_body[0] != 0xAA:
                debug_log('Protocol warning: '
                          'Initial frame of packet is missing synchronization.')
            if frame_body[1] != 0x12 and frame_body[1] != 0x21:
                debug_log('Protocol warning: '
                          'Direction is neither computer to charger nor charger to computer, '
                          'but 0x{:02X}'.format(frame_body[1]))
            expected_packet_length = frame_body[2]
            packet_data = __unescape_synchronization__(frame_body[1:])
        else:
            packet_data.extend(__unescape_synchronization__(frame_body))

    # We read _at least_ enough data to match the announced length plus header plus checksum,
    # and then we cut the actual payload out of it. The following byte will be the checksum.

    checksum_from_packet: int = packet_data[expected_packet_length + 2]
    packet_data = packet_data[:expected_packet_length + 2]
    checksum: int = 0x00
    for b in packet_data:
        checksum = (checksum + b) & 0xFF

    if checksum != checksum_from_packet:
        debug_log('Protocol warning: Checksum wrong. calculated 0x{:02X}, in packet 0x{:02X}.'
                  .format(checksum, checksum_from_packet))

    return packet_data[2:]  # The first 2 bytes aren't payload.
