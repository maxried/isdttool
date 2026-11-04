# coding=utf-8

"""Transports carry raw 64-byte HID reports between isdttool and a charger.

The Charger class does not care how the reports travel. A transport only has to offer the
subset of the hidapi device interface that the Charger uses:

* read(max_length, timeout_ms) returns one report, or an empty result on timeout,
* write(data) sends one report,
* close().

UsbTransport talks to a charger on a local USB port through hidapi. TcpTransport talks to a
charger that is exposed on the network by a bridge.

The TCP wire format is deliberately minimal, so that the two sides stay independent: every
message in both directions is exactly one 64-byte report, exactly as it would be passed to or
returned from hidapi. There is no handshake, no framing, and no other message type. One TCP
port serves one charger.
"""

import socket
from typing import Optional

REPORT_SIZE = 64
DEFAULT_TCP_PORT = 24000


class UsbTransport:
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

    def read(self, max_length: int = REPORT_SIZE, timeout_ms: int = 0) -> bytes:
        """
        Reads one report.
        :param max_length: The maximum number of bytes to return.
        :param timeout_ms: How long to wait for a report. 0 waits forever.
        :return: The report, or an empty result on timeout.
        """
        return bytes(self.__device__.read(max_length, timeout_ms))

    def write(self, data: bytes) -> int:
        """
        Writes one report.
        :param data: The report.
        :return: The number of bytes written.
        """
        return self.__device__.write(data)

    def close(self) -> None:
        """Closes the device."""
        self.__device__.close()


class TcpTransport:
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
        # A report may arrive in several TCP segments. Bytes of a report that was not complete
        # when a read timed out are kept here for the next read.
        self.__buffer__ = bytearray()

    def read(self, max_length: int = REPORT_SIZE, timeout_ms: int = 0) -> bytes:
        """
        Reads one report.
        :param max_length: The maximum number of bytes to return.
        :param timeout_ms: How long to wait for a report. 0 waits forever.
        :return: The report, or an empty result on timeout.
        :raises ConnectionError: if the bridge closed the connection.
        """
        self.__socket__.settimeout(timeout_ms / 1000 if timeout_ms > 0 else None)

        while len(self.__buffer__) < REPORT_SIZE:
            try:
                chunk = self.__socket__.recv(REPORT_SIZE - len(self.__buffer__))
            except socket.timeout:
                return b''
            if not chunk:
                raise ConnectionError('The bridge closed the connection.')
            self.__buffer__.extend(chunk)

        report = bytes(self.__buffer__[:REPORT_SIZE])
        del self.__buffer__[:REPORT_SIZE]
        return report[:max_length]

    def write(self, data: bytes) -> int:
        """
        Writes one report. Shorter reports are padded with zeros, like hidapi does.
        :param data: The report, at most 64 bytes.
        :return: The number of bytes written.
        """
        if len(data) > REPORT_SIZE:
            raise ValueError('A report is at most {} bytes, got {}.'
                             .format(REPORT_SIZE, len(data)))
        report = bytes(data) + b'\x00' * (REPORT_SIZE - len(data))
        self.__socket__.settimeout(None)
        self.__socket__.sendall(report)
        return REPORT_SIZE

    def close(self) -> None:
        """Closes the connection."""
        self.__socket__.close()
