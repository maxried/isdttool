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
    """The csv.DictWriter seems to have some serious quirks when using it to write to stdout.
    E.g. redirection works, piping does not. So here you go. It's just a wrapper around print
    with some minor adjustments to the parameters. """
    @staticmethod
    def write(*args, **kwargs) -> None:
        """This is an implementation of the Python file protocol just enough to use it with
        csv.DictWriter. """
        kwargs['flush'] = True
        kwargs['end'] = ''
        print(*args, **kwargs)


def assure_compatibility(charger: Charger, configurations: List[Tuple[str, str]]) -> bool:
    """
    This ensures compatibility, and provides a proper error message if a command is not supported.
    If debug_mode is True, this skips the check, and always returns True.
    :param charger: The charger to test.
    :param configurations: A list of tuples like [('A4', 'boot'), ('C4', 'app')]
    :return: True, if charger matches.
    """
    for model, mode in configurations:
        if charger.model in (model, 'ignore') and charger.mode in (mode, 'ignore'):
            return True

    print('This command is currently not supported by the model "{}" in {} mode.\n'
          'The command is supported in the following modes:'.format(charger.model, charger.mode),
          file=sys.stderr)
    for i in configurations:
        print('Model "{}" in {} mode'.format(i[0], i[1]), file=sys.stderr)

    return False


def print_simple_result(charger: Charger, output_mode: str = 'text') -> None:
    """
    Print the result of the simpler commands, e.g. version, or link-test
    :param charger: The charger to read from.
    :param output_mode: The presentation format.
    """
    result = charger.read_packet()
    if result is None:
        print('Charger returned no result.', file=sys.stderr)
        return
    else:
        if output_mode == 'text':
            print(packet_to_str(result, charger.model))
        elif output_mode == 'dict':
            print(parse_packet(result, charger.model))
        elif output_mode == 'json':
            print(json.dumps(parse_packet(result, charger.model)))
        elif output_mode == 'csv':
            result = parse_packet(result, charger.model)
            writer = csv.DictWriter(RedirectWriteToPrint(), result.keys())
            writer.writeheader()
            writer.writerow(result)
        elif output_mode == 'raw':
            print(' '.join(f'{x:02x}' for x in result))
        else:
            raise ValueError('Output mode "{}" is not implemented.'.format(output_mode))


def display_link_test(charger: Charger, output_mode='text') -> None:
    """
    Sends a nop command, and displays a message stating if it was transmitted, and acknowledged.
    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    # This one is assumed to be always supported.
    # If it wasn't the verification would not work at all.
    charger.link_test()
    print_simple_result(charger, output_mode)


def rename_device(charger: Charger, name: str = '', output_mode: str = 'text') -> None:
    """
    Renames the device. This causes an immediate reboot. It takes a maximum of eight characters.
    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param name: The new name of the device. Will be truncated to 8 bytes. No sanity check. Use
    with care.
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('Q8', 'app')]):
        return

    charger.rename_device(name)
    print_simple_result(charger, output_mode)


def read_serial_number(charger: Charger, output_mode='text') -> None:
    """
    Retrieves the permanent serial number of the device, e.g. the unique device ID register of
    the builtin MCU.
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
       Queries the state of the charging channel.
       :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
       :param interval: How many seconds to wait between queries.
       :param count: Stop after that many queries.
       :param channels: List of the zero-indexed channel numbers to query.
       :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('A4', 'app'), ('C4EVO', 'app')]):
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
                    print(packet_to_str(result, charger.model))
                elif output_mode == 'dict':
                    print(parse_packet(result, charger.model))
                elif output_mode == 'json':
                    result_dict = parse_packet(result, charger.model)
                    result_dict['_measurement'] = step
                    all_channels.append(result_dict)
                elif output_mode == 'csv':
                    result_dict = parse_packet(result, charger.model)
                    if first:
                        writer = csv.DictWriter(RedirectWriteToPrint(), result_dict.keys())
                        writer.writeheader()
                        first = False
                    writer.writerow(result_dict)
                elif output_mode == 'raw':
                    print(' '.join(f'{x:02x}' for x in result))

            if count == 0 or count - step != 0:
                sleep(interval)
    except KeyboardInterrupt:
        pass

    if output_mode == 'json':
        print(json.dumps(all_channels))


def display_version(charger: Charger, output_mode='text') -> None:
    """
    Queries the software versions, and model of the charger.
    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    # This one is assumed to be always supported.
    # If it wasn't the verification would not work at all.

    charger.version()
    print_simple_result(charger, output_mode)


def reboot_to_boot_loader(charger: Charger, output_mode='text') -> None:
    """
    Reboots the charger to boot loader mode.
    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('A4', 'app'), ('C4', 'boot loader'),
                                          ('A4', 'boot loader'), ('C4EVO', 'app'),
                                          ('C4EVO', 'boot loader')]):
        return

    charger.boot_to_loader()
    print_simple_result(charger, output_mode)


def verify_firmware(charger: Charger, file: BinaryIO, output_mode: str = 'text'):
    """
    This verifies if the firmware image that is flashed to the charger has the same checksum as
    the one inside the file.
    :param charger: What charger to check
    :param file: The encrypted file as downloaded from ISDT
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'boot loader'), ('A4', 'boot loader'),
                                          ('C4EVO', 'boot loader')]):
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
       Queries the state of some sensors. I hardly know what they mean.
       :param charger: what charger to ask
       :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app')]):
        return

    charger.read_some_sensors()
    print_simple_result(charger, output_mode)


def display_channel_sensors(charger: Charger, channel: int, output_mode='text') -> None:
    """
       Queries the state of some channel sensors on C4EVO
       :param charger: what charger to ask
       :param channel: channel ID, 0 indexed
       :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4EVO', 'app')]):
        return

    charger.channel_sensors(channel)
    print_simple_result(charger, output_mode)


def display_channel_voltages(charger: Charger, output_mode='text') -> None:
    """
       Queries the state of some channel voltages on Q8.
       :param charger: what charger to ask
       :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('Q8', 'app')]):
        return

    charger.channel_voltages()
    print_simple_result(charger, output_mode)


def reboot_to_app(charger: Charger, output_mode='text') -> None:
    """
    Reboots the charger to app mode.
    :param charger: An usb.Device object for the charger as retrieved by isdttool.get_device
    :param output_mode: Either csv, test, json, or dict.
    """
    if not assure_compatibility(charger, [('C4', 'app'), ('A4', 'app'), ('C4', 'boot loader'),
                                          ('A4', 'boot loader'), ('C4EVO', 'app'),
                                          ('C4EVO', 'boot loader')]):
        return

    charger.boot_to_app()
    print_simple_result(charger, output_mode)


def write_raw_command(charger: Charger, command: bytearray, output_mode: str = 'text'):
    """
    Sends a raw command to the charger. Don't use this.
    :param charger: The charger to ask.
    :param command: List of ints representing each byte of the command.
    :param output_mode: Either csv, test, json, or dict.
    """
    # Of course, this one doesn't care at all for compatibility.

    print('About to write command: {}'.format(' '.join(f'{x:02x}' for x in command)))
    charger.write_to_charger(command)
    print('Sent.')
    print_simple_result(charger, output_mode)


def monitor_state(charger: Charger,
                  func: Callable[[Optional[Dict[str, Union[str, int, bool]]],
                                  Dict[str, Union[str, int, bool]]], None],
                  interval: float, period: Optional[int]) -> None:
    """
    Calls func with the parsed metrics packet if something changed, or the optional period has
    passed. Never stops, unless there is an unrecoverable exception.
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
        c_state = parse_packet(charger.read_packet(), charger.model)
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
            current_state.append(parse_packet(charger.read_packet(), charger.model))

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
