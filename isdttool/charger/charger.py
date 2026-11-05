# coding=utf-8

"""This file contains functions to parse incoming packets, and to construct outgoing packets.
It cares about checksums, and stuff."""
from typing import Optional, List, Tuple

from .framing import debug_log, decode_frames, __escape_synchronization__, \
    __unescape_synchronization__, __generate_raw_frames__
from .representation import parse_packet
from .transport import Transport, UsbTransport, TcpTransport, DEFAULT_TCP_PORT


class Charger:
    """Represents a charger. Basically only wraps a transport (see transport.py), and supplies
    read/write functions. """

    def __init__(self, device: Optional[Transport], model: str, mode: str,
                 read_timeout_ms: int = 200) -> None:
        self.__device__ = device
        self.model = model
        self.mode = mode
        # How long to wait for a reply, or for each USB frame of it. Chargers usually answer
        # within 20 ms, but a busy N24 takes up to about 260 ms now and then.
        self.read_timeout_ms = read_timeout_ms

        if self.model == 'auto' or self.mode == 'auto':
            if self.__device__ is not None:
                model_mode = self.model_and_mode()
                if self.model == 'auto':
                    self.model = model_mode[0]
                if self.mode == 'auto':
                    self.mode = model_mode[1]
            else:
                raise ValueError('Cannot auto query model or mode if device is None.')

    def read_packet(self, captured_frames: Optional[List[bytearray]] = None) \
            -> Optional[bytearray]:
        """
        Tries to read a packet from the charger. Use it to get the results.
        :param captured_frames: This here must contain captured USB frames. Only useful for
        testing. If omitted, the function reads from the charger.
        :return: The packet data, or None if the charger didn't answer in time.
        """
        if captured_frames is not None:
            return decode_frames(lambda: captured_frames.pop(0))  # This is for unit-testing.

        packet = self.__device__.receive(self.read_timeout_ms)
        return None if packet is None else bytearray(packet)

    def write_to_charger(self, payload: bytearray) -> None:
        """
        This function is the user facing interface for packet writing. It takes care
        about everything, including actually sending it.
        :param payload: The packet data to send to the device. Must be smaller than 255 bytes.
        """
        self.__device__.send(bytes(payload))

    def close(self) -> None:
        """
        Closes the connection to the charger.
        """
        if self.__device__ is not None:
            self.__device__.close()

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
               path: Optional[str] = None, host: Optional[str] = None,
               port: Optional[int] = None,
               read_timeout_ms: Optional[int] = None) -> Charger:
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
    :param host: Connect over TCP to a bridge on this host, instead of opening a local USB
    device. Mutually exclusive with path, product_id, and vendor_id.
    :param port: TCP port of the bridge. Defaults to 24000. Only used with host.
    :param read_timeout_ms: How long to wait for a reply, or for each USB frame of it. Defaults
    to 200 ms over USB, and 1000 ms over TCP, which adds the network to the charger's own delay.
    """
    if host is not None:
        if path is not None or product_id is not None or vendor_id is not None:
            raise ValueError('host is mutually exclusive with path, product_id, and vendor_id.')
        transport: Transport = TcpTransport(host, DEFAULT_TCP_PORT if port is None else port)
    else:
        transport = UsbTransport(path=path, vendor_id=vendor_id, product_id=product_id)

    if read_timeout_ms is None:
        read_timeout_ms = 1000 if host is not None else 200

    return Charger(model=model_name, mode=mode, device=transport,
                   read_timeout_ms=read_timeout_ms)


def enumerate_devices(vendor_id: int = 0x28e9, product_id: int = 0x028a):
    """Just wraps the hid.enumerate function
    :param product_id: Fill in the product id. Hint: It's always 0x028a.
    :param vendor_id: Fill in the vendor id. Hint: It's always 0x28e9
    """
    # noinspection PyPackageRequirements
    import hid

    return hid.enumerate(vendor_id, product_id)
