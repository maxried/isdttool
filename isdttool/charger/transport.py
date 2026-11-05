# coding=utf-8

"""Transports carry packets between isdttool and a charger.

A packet is what the Charger class sends and receives: a command or a response, starting with
its opcode, e.g. 0xe0 for the version request and 0xe1 for its response. How a packet travels
depends on the link, so that is up to the transport:

* UsbTransport wraps packets in the USB framing (see framing.py), and talks to a charger on a
  local USB port through hidapi.
* TcpTransport talks to a charger that a bridge exposes on the network.

Other links fit the same interface. A Bluetooth LE transport, for example, would write the
packet to a GATT characteristic behind a direction byte, and return the notifications without
their direction byte.

The TCP wire format is deliberately minimal, so that the two sides stay independent: in both
directions, every message is one packet, preceded by its length as two bytes, big-endian.
There is no handshake, and no other message type. One TCP port serves one charger, whatever
link the bridge uses to reach it.
"""

import socket
import struct
from typing import Optional

from .framing import __generate_raw_frames__, decode_frames, debug_log

REPORT_SIZE = 64
DEFAULT_TCP_PORT = 24000
MAX_TCP_PACKET_SIZE = 0xffff


class Transport:
    """The interface of all transports."""

    def send(self, packet: bytes) -> None:
        """
        Sends one packet to the charger.
        :param packet: The packet, starting with its opcode.
        """
        raise NotImplementedError

    def receive(self, timeout_ms: int) -> Optional[bytes]:
        """
        Receives one packet from the charger.
        :param timeout_ms: How long to wait for the packet. Transports that receive a packet in
        pieces may apply it to each piece.
        :return: The packet, starting with its opcode, or None on timeout.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Closes the link to the charger."""
        raise NotImplementedError


class UsbTransport(Transport):
    """A charger on a local USB port, opened through hidapi."""

    def __init__(self, path: Optional[str] = None, vendor_id: Optional[int] = None,
                 product_id: Optional[int] = None) -> None:
        """
        Opens the charger.
        :param path: hid path. Platform specific format. Mutually exclusive with vendor_id,
        and product_id.
        :param vendor_id: USB vendor id of the device to open.
        :param product_id: USB product id of the device to open.
        """
        # Imported here, so that hidapi is only needed when a charger is opened over USB.
        # noinspection PyPackageRequirements
        import hid

        self.__device__ = hid.device()
        if path is not None:
            self.__device__.open_path(bytes(path, encoding='utf8'))
        else:
            self.__device__.open(vendor_id=vendor_id, product_id=product_id)

    def send(self, packet: bytes) -> None:
        """
        Sends one packet, in as many reports as it takes.
        :param packet: The packet, at most 255 bytes.
        """
        frames = __generate_raw_frames__(bytearray(packet))
        debug_log('Writing', len(packet), 'bytes, split into', len(frames), 'frames.')
        for frame in frames:
            frame.extend(b'\x00' * (REPORT_SIZE - len(frame)))
            debug_log('Writing', bytes(frame).hex())
            self.__device__.write(frame)

    def receive(self, timeout_ms: int) -> Optional[bytes]:
        """
        Receives one packet.
        :param timeout_ms: How long to wait for each report of the packet.
        :return: The packet, or None on timeout.
        """
        packet = decode_frames(lambda: bytes(self.__device__.read(REPORT_SIZE, timeout_ms)))
        return None if packet is None else bytes(packet)

    def close(self) -> None:
        """Closes the device."""
        self.__device__.close()


def encode_tcp_packet(packet: bytes) -> bytes:
    """
    Puts one packet into the TCP wire format.
    :param packet: The packet.
    :return: The length of the packet, and the packet.
    """
    if len(packet) > MAX_TCP_PACKET_SIZE:
        raise ValueError('A packet is at most {} bytes, got {}.'
                         .format(MAX_TCP_PACKET_SIZE, len(packet)))
    return struct.pack('>H', len(packet)) + bytes(packet)


def take_tcp_packet(buffer: bytearray) -> Optional[bytes]:
    """
    Takes the first packet out of received TCP data, if it has arrived completely.
    :param buffer: The data received so far. The packet is removed from it.
    :return: The packet, or None if it hasn't arrived completely yet.
    """
    if len(buffer) < 2:
        return None
    length = struct.unpack('>H', buffer[:2])[0]
    if len(buffer) < 2 + length:
        return None
    packet = bytes(buffer[2:2 + length])
    del buffer[:2 + length]
    return packet


class TcpTransport(Transport):
    """A charger exposed on the network by a bridge, reached over TCP."""

    def __init__(self, host: str, port: int = DEFAULT_TCP_PORT,
                 connect_timeout: float = 5.0) -> None:
        """
        Connects to the bridge.
        :param host: Host name, IPv4 address, or IPv6 address of the bridge.
        :param port: TCP port of the bridge. Each port serves one charger.
        :param connect_timeout: How long to wait for the connection, in seconds.
        """
        self.__socket__ = socket.create_connection((host, port), timeout=connect_timeout)
        self.__socket__.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # A packet may arrive in several TCP segments. Bytes of a packet that was not complete
        # when a read timed out are kept here for the next read.
        self.__buffer__ = bytearray()

    def send(self, packet: bytes) -> None:
        """
        Sends one packet.
        :param packet: The packet, at most 65535 bytes.
        """
        data = encode_tcp_packet(packet)
        debug_log('Writing', data.hex())
        self.__socket__.settimeout(None)
        self.__socket__.sendall(data)

    def receive(self, timeout_ms: int) -> Optional[bytes]:
        """
        Receives one packet.
        :param timeout_ms: How long to wait for each part of the packet. 0 waits forever.
        :return: The packet, or None on timeout.
        :raises ConnectionError: if the bridge closed the connection.
        """
        self.__socket__.settimeout(timeout_ms / 1000 if timeout_ms > 0 else None)

        while True:
            packet = take_tcp_packet(self.__buffer__)
            if packet is not None:
                debug_log('Reading', packet.hex())
                return packet
            try:
                chunk = self.__socket__.recv(4096)
            except socket.timeout:
                return None
            if not chunk:
                raise ConnectionError('The bridge closed the connection.')
            self.__buffer__.extend(chunk)

    def close(self) -> None:
        """Closes the connection."""
        self.__socket__.close()
