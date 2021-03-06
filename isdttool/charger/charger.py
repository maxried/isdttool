# coding=utf-8

"""This file contains functions to parse incoming packets, and to construct outgoing packets.
It cares about checksums, and stuff."""
import sys
from typing import Optional, List, Tuple

# noinspection PyPackageRequirements
import hid

import isdttool
from .representation import parse_packet


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


class Charger:
    """Represents a charger. Basically only wraps an hid device, and supplies read/write
    functions. """

    def __init__(self, device: Optional[hid.device], model: str, mode: str) -> None:
        self.__device__ = device
        self.model = model
        self.mode = mode

        if self.model == 'auto' or self.mode == 'auto':
            if self.__device__ is not None:
                model_mode = self.model_and_mode()
                if self.model == 'auto':
                    self.model = model_mode[0]
                if self.mode == 'auto':
                    self.mode = model_mode[1]
            else:
                raise ValueError('Cannot auto query model or mode if device is None.')

    def read_packet(self, captured_frames: Optional[List[bytearray]] = None) -> bytearray:
        """
        Tries to read a packet from the charger. Use it to get the results. If you call it,
        and there is nothing to read it will throw an exception.
        :param captured_frames: This here must contain captured frames. Only useful for testing.
        If omitted, the function reads from the charger.
        :return: The packet data. Reassembled, unescaped, and checked for errors.
        """

        expected_packet_length: Optional[int] = None
        packet_data: Optional[bytearray] = None

        # We read 3 bytes more than we think we need, because the packet length as stated in the
        # packet does not contain the header of the packet, and its checksum.
        while expected_packet_length is None or len(packet_data) < expected_packet_length + 3:
            frame_as_received: Optional[bytearray]
            if captured_frames is None:
                try:
                    frame_as_received: bytearray = bytearray(
                        self.__device__.read(max_length=64, timeout_ms=200))
                except OSError as e:  # While this seems useless, it reminds me it may raise
                    # exceptions on timeout.
                    raise e
                debug_log('Reading', bytes(frame_as_received).hex())
            else:
                frame_as_received = captured_frames.pop(0)  # This is for unit-testing.
                debug_log('Using user provided frame:', bytes(frame_as_received).hex())

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

    def write_to_charger(self, payload: bytearray) -> None:
        """
        This function is the user facing interface for packet writing. It takes care
        about everything, including actually sending it.
        :param payload: The packet data to send to the device. Must be smaller than 255 bytes.
        """
        frames = __generate_raw_frames__(payload)
        debug_log('Writing', len(payload), 'bytes, split into', len(frames), 'frames.')
        for f in frames:
            f.extend(b'\x00' * (64 - len(f)))
            debug_log('Writing', bytes(f).hex())
            self.__device__.write(f)

    def link_test(self) -> None:
        """
        Sends a well-supported nop command.
        """
        self.write_to_charger(bytearray([0x00]))

    def rename_device(self, new_name: str):
        """
        Renames the device. This causes an immediate reboot. It takes a maximum of 8 characters.
        :param new_name: The new name, maximum 8 chars, might be UTF-8.
        """
        encoded_name: bytes = new_name.encode(encoding='utf8')
        command: bytearray = bytearray([0xc0])
        command.extend(encoded_name)
        command.extend(b'\x00' * 8)
        self.write_to_charger(command[0:9])

    def get_mcu_serial_number(self) -> None:
        """
        Requests the value of the unique device ID register of the STM32-like MCU.
        See ST's RM0008, sec. 30.2
        """
        self.write_to_charger(bytearray([0xc8]))

    def metrics(self, channel: int) -> None:
        """
        Requests metrics for a charging channel.
        :param channel: 0-indexed channel number
        """
        self.write_to_charger(bytearray([0xde, channel]))

    def version(self) -> None:
        """
        Requests version information from the charger.
        """
        self.write_to_charger(bytearray([0xe0]))

    def boot_to_loader(self) -> None:
        """
        Immediately reboots the charger to boot loader mode.
        """
        self.write_to_charger(bytearray([0xf0, 0xac]))

    def verify_firmware(self, app_storage_offset: int, app_size: int, calculated_checksum: int) \
            -> None:
        """
        Requests a verification of the firmware.
        :param app_storage_offset: The in-memory address to start the verification.
        :param app_size: The length of the data to verify, really should be a multiple of 4.
        :param calculated_checksum: uint32 sum of the firmware treated as an array of uint32
        :return:
        """
        cmd = bytearray(b'\xf6\x35\x00')
        cmd.extend(int.to_bytes(app_storage_offset, signed=False, length=4, byteorder='little'))
        cmd.extend(int.to_bytes(app_size, signed=False, length=4, byteorder='little'))
        cmd.extend(int.to_bytes(calculated_checksum, signed=False, length=4, byteorder='little'))
        self.write_to_charger(cmd)

    def read_some_sensors(self) -> None:
        """
        Reads some sensor value whose meaning remains partially unknown.
        """
        self.write_to_charger(bytearray([0xf8]))

    def channel_sensors(self, channel: int) -> None:
        """
        Reads some channel measurements. Found on C4EVO.
        """
        self.write_to_charger(bytearray([0xe4, channel]))

    def channel_voltages(self) -> None:
        """
        Reads some channel measurements. Like channel_sensors, but without parameter. Found on Q8.
        """
        self.write_to_charger(bytearray([0xe4]))

    def boot_to_app(self) -> None:
        """
        Immediately reboots the charger to app mode.
        """
        self.write_to_charger(bytearray([0xfc, 0xca]))

    def model_and_mode(self) -> Tuple[str, str]:
        """
        Returns the model, and mode. You are responsible to ensure that the charger supports
        the command you send it. This might help you.
        :return: A 2-tuple consisting of the model name,
        and either 'boot loader', or 'app'. None, if something broke.
        """
        self.link_test()
        link_test_result = parse_packet(self.read_packet(), 'ignore')
        self.version()
        version_result = parse_packet(self.read_packet(), 'ignore')
        return version_result['model name'], ('boot loader'
                                              if link_test_result['inside boot loader'] else 'app')


def get_device(model_name: str = 'auto', mode: str = 'auto',
               product_id: Optional[int] = None, vendor_id: Optional[int] = None,
               path: Optional[str] = None) -> Charger:
    """
    Looks for a charger, and returns the first one found. This deserves a little more
    sophistication. Both C4, and A4 share the same IDs. Additionally, the A4 identifies itself
    as C4 in the USB descriptor. To distinguish both, you have to ask it.
    :param model_name: The model name will be passed to the charger class.
    :param mode: The mode that will be passed to the charger class.
    :param product_id: USB product id of the device to open. Mutually exclusive with path.
    :param vendor_id: USB vendor_id id of the device to open. Mutually exclusive with path.
    :param path: hid path. Platform specific format. Refer to `hidtest`, or the hidapi
    documentation. Mutually exclusive with product_id, and vendor_id.
    """
    hid_device = hid.device()

    if path is not None:
        hid_device.open_path(bytes(path, encoding='utf8'))
    else:
        hid_device.open(vendor_id=vendor_id, product_id=product_id)

    return Charger(model=model_name, mode=mode, device=hid_device)


def enumerate_devices(vendor_id: int = 0x28e9, product_id: int = 0x028a):
    """Just wraps the hid.enumerate function
    :param product_id: Fill in the product id. Hint: It's always 0x028a.
    :param vendor_id: Fill in the vendor id. Hint: It's always 0x28e9
    """
    return hid.enumerate(vendor_id, product_id)
