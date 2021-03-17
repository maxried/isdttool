# coding=utf-8

"""Command wrapper functions to easily interface with the charger."""

import csv
import json
import sys
from io import BytesIO
from time import sleep
from typing import BinaryIO, Dict, List, Optional, Union, Tuple, Callable

import isdttool
from .charger import Charger
from .representation import packet_to_str, parse_packet
from ..firmware import decrypt_firmware_image


class RedirectWriteToPrint:
    """
    The csv.DictWriter seems to have some serious quirks when using it to write to stdout.

    E.g. redirection works, piping does not. So here you go. It's just a wrapper around print
    with some minor adjustments to the parameters.
    """

    @staticmethod
    def write(*args, **kwargs) -> None:
        """Implementation of the file protocol just enough to use it with csv.DictWriter."""
        kwargs['flush'] = True
        kwargs['end'] = ''
        print(*args, **kwargs)


def assure_compatibility(charger: Charger, configurations: List[Tuple[str, str]],
                         silent: bool = False) -> bool:
    """
    Verify compatibility, and provide a proper error message if a command is not supported.

    If debug_mode is True, the check is skipped, and True is returned.

    :param charger: The charger to test.
    :param configurations: A list of tuples like [('A4', 'boot'), ('C4', 'app')]
    :param silent: If True, don't print out error messages.
    :return: True, if charger matches, or debug mode is activated.
    """
    if isdttool.DEBUG_MODE:
        return True

    my_model = charger.model_and_mode()
    if my_model not in configurations:
        if not silent:
            print('This command is currently not supported by the model "{}" in {} mode.\n'
                  'The command is supported in the following modes:'
                  .format(my_model[0], my_model[1]), file=sys.stderr)
            for i in configurations:
                print('Model "{}" in {} mode'.format(i[0], i[1]), file=sys.stderr)

        return False

    return True


def print_simple_result(charger: Charger, output_mode: str = 'text') -> None:
    """
    Print the result of the simpler commands, e.g. version, or link-test.

    :param charger: The charger to read from.
    :param output_mode: The presentation format.
    """
    result = charger.read_packet()
    if result is None:
        print('Charger returned no result.', file=sys.stderr)
        return
    else:
        if output_mode == 'text':
            print(packet_to_str(result))
        elif output_mode == 'dict':
            print(parse_packet(result))
        elif output_mode == 'json':
            print(json.dumps(parse_packet(result)))
        elif output_mode == 'csv':
            result = parse_packet(result)
            writer = csv.DictWriter(RedirectWriteToPrint(), result.keys())
            writer.writeheader()
            writer.writerow(result)
        elif output_mode == 'raw':
            print(result.hex())
        else:
            raise ValueError('Output mode "{}" is not implemented.'.format(output_mode))


def display_link_test(charger: Charger, output_mode='text') -> None:
    """
    Send a nop command, and display a message stating if it was transmitted, and acknowledged.

    :param charger: A usb.Device object for the charger as retrieved by isdttool.get_device.
    :param output_mode: Either csv, test, json, or dict.
    """
    # This one is assumed to be always supported.
    # If it wasn't the verification would not work at all.
    charger.link_test()
    print_simple_result(charger, output_mode)


def rename_device(charger: Charger, name: str = '', output_mode: str = 'text') -> None:
    """
    Rename the device.

    This causes an immediate reboot, no exceptions. It takes a maximum of eight characters.

    :param charger: A usb.Device object for the charger as retrieved by isdttool.get_device.
    :param name: The new name of the device. Will be truncated to 8 bytes. No sanity check. Use
    with care.
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app')]):
        return

    charger.rename_device(name)
    print_simple_result(charger, output_mode)


def read_serial_number(charger: Charger, output_mode='text') -> None:
    """
    Retrieve the permanent serial number of the device.

    This is the unique device ID register of the builtin MCU.

    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('A4', 'app')]):
        return

    charger.get_mcu_serial_number()
    print_simple_result(charger, output_mode)


def display_metrics(charger: Charger, interval: float, count: int, channels: List[int],
                    output_mode='text') -> None:
    """
    Query the state of the charging channel.

    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param interval: How many seconds to wait between queries.
    :param count: Stop after that many queries.
    :param channels: List of the zero-indexed channel numbers to query.
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('A4', 'app')]):
        return

    step: int = 0
    all_channels: List[Dict[str, Union[str, int, bool]]] = []
    first: bool = True
    writer: Optional[csv.DictWriter] = None

    try:
        while count == 0 or step < count:
            step += 1

            for i in channels:
                charger.metrics(i)
                result: bytearray
                result = charger.read_packet()

                if output_mode == 'text':
                    print(packet_to_str(result))
                elif output_mode == 'dict':
                    print(parse_packet(result))
                elif output_mode == 'json':
                    result_dict = parse_packet(result)
                    result_dict['_measurement'] = step
                    all_channels.append(result_dict)
                elif output_mode == 'csv':
                    result_dict = parse_packet(result)
                    if first:
                        writer = csv.DictWriter(RedirectWriteToPrint(), result_dict.keys())
                        writer.writeheader()
                        first = False
                    writer.writerow(result_dict)
                elif output_mode == 'raw':
                    print(result.hex())

            if count == 0 or count - step != 0:
                sleep(interval)
    except KeyboardInterrupt:
        pass

    if output_mode == 'json':
        print(json.dumps(all_channels))


def display_version(charger: Charger, output_mode='text') -> None:
    """
    Query the software versions, and the model name of the charger.

    :param charger: A usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    # This one is assumed to be always supported.
    # If it wasn't the verification would not work at all.

    charger.version()
    print_simple_result(charger, output_mode)


def reboot_to_boot_loader(charger: Charger, output_mode='text') -> None:
    """
    Reboot the charger to bootloader mode.

    :param charger: A usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('A4', 'app'), ('C4', 'bootloader'),
                                          ('A4', 'bootloader')]):
        return

    charger.boot_to_loader()
    print_simple_result(charger, output_mode)


def verify_firmware(charger: Charger, file: BinaryIO, output_mode: str = 'text'):
    """
    Verify if the firmware on the charger has the same checksum as the one inside the file.

    :param charger: What charger to check
    :param file: The encrypted file as downloaded from ISDT
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'bootloader'), ('A4', 'bootloader')]):
        return

    decrypted_firmware = BytesIO()
    header: Dict[str, int] = decrypt_firmware_image(file, decrypted_firmware)
    if 'app_storage_offset' in header.keys() and \
            'app_size' in header.keys() and \
            'calculated_checksum' in header.keys():
        charger.verify_firmware(header['app_storage_offset'],
                                header['app_size'],
                                header['calculated_checksum'])
        print_simple_result(charger, output_mode)
    else:
        print('Could not verify firmware image, because the header could not be read.')


def display_sensors(charger: Charger, output_mode='text') -> None:
    """
    Query the state of some sensors.

    I hardly know what they mean.

    :param charger: what charger to ask
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app')]):
        return

    charger.read_some_sensors()
    print_simple_result(charger, output_mode)


def reboot_to_app(charger: Charger, output_mode='text') -> None:
    """
    Reboot the charger to app mode.

    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('A4', 'app'), ('C4', 'bootloader'),
                                          ('A4', 'bootloader')]):
        return

    charger.boot_to_app()
    print_simple_result(charger, output_mode)


def write_raw_command(charger: Charger, command: List[int], output_mode: str = 'text'):
    """
    Send a raw command to the charger.

    Don't use this.

    :param charger: The charger to ask.
    :param command: List of ints representing each byte of the command.
    :param output_mode: Either csv, test, json, or dict.
    """
    # Of course, this one doesn't care at all for compatibility.

    payload: bytearray = bytearray()
    for c in command:
        if not 0 <= c <= 255:
            print('{} is out of range.'.format(c))
            return
        payload.append(c)

    print('About to write command: {}'.format(bytes(payload).hex()))
    charger.write_to_charger(payload)
    print('Sent.')
    print_simple_result(charger, output_mode)


def monitor_state(charger: Charger,
                  func: Callable[[Optional[Dict[str, Union[str, int, bool]]],
                                  Dict[str, Union[str, int, bool]]], None],
                  interval: float, period: Optional[int]) -> None:
    """
    Call func with the parsed metrics packet if something changed.

    Also does this if the optional period has passed.
    Never stops, unless there is an unrecoverable exception.

    :param charger: The charger to poll.
    :param func: The function to call. Must accept a Dict, shouldn't return anything.
    The call reason can be read from the result key '_reason'.
    :param interval: How often to poll the charger.
    :param period: How often to call func if even if nothing has changed. This is in multiples of
    interval. Ignored if None.
    """
    state: List[Dict[str, Union[str, int, bool]]] = []
    max_channel: Optional[int] = None

    # Discover channel count

    for i in range(0, 256):
        charger.metrics(i)
        c_state = parse_packet(charger.read_packet())
        if c_state['_channel exists']:
            max_channel = i
            state.append(c_state)
            func(None, {**{'_reason': 'channel id', '_channel': i}, **c_state})
        else:
            break

    if max_channel is None:
        func(None, {'_reason': 'no channels'})
        return

    current_iteration: int = 0

    while True:
        current_iteration += 1

        current_state: List[Dict[str, Union[str, int, bool]]] = []
        for i in range(0, max_channel + 1):
            charger.metrics(i)
            current_state.append(parse_packet(charger.read_packet()))

        if period is not None and current_iteration % period == 0:
            for c in current_state:
                c['_reason'] = 'periodic'
                func(None, c)

        for comp in zip(state, current_state):
            comp[1]['_iteration'] = current_iteration

            if comp[0]['mode id'] != comp[1]['mode id']:
                comp[1]['_reason'] = 'mode id'
                func(comp[0], comp[1])

            if comp[0]['chemistry id'] != comp[1]['chemistry id']:
                comp[1]['_reason'] = 'chemistry id'
                func(comp[0], comp[1])

            if comp[0]['dimensions id'] != comp[1]['dimensions id']:
                comp[1]['_reason'] = 'dimensions id'
                func(comp[0], comp[1])

        state = current_state
        sleep(interval)
