#!/usr/bin/env python3
# coding=utf-8

"""Retrieve measurements, and such from an ISDT charger."""

import argparse
import sys
from argparse import ArgumentParser

from typing import BinaryIO, Union, Dict, Callable

import isdttool
from isdttool import get_device
from isdttool.charger import display_metrics, display_version, display_link_test, \
    reboot_to_boot_loader, \
    reboot_to_app, rename_device, display_sensors, write_raw_command, verify_firmware, \
    read_serial_number, \
    monitor_state
from isdttool.firmware import decrypt_firmware_image, print_firmware_info


def firmware_decrypt(encrypted: BinaryIO, output: BinaryIO) -> None:
    """
    Decrypt the firmware file, and show the checksums.

    :param encrypted: IO (aka file) to read the fw from
    :param output: IO (aka file) to write the fw to
    """
    header = decrypt_firmware_image(encrypted, output)

    print('Embedded checksum:     0x{0:08x}'.format(header['embedded_checksum']))
    print('Calculated checksum:   0x{0:08x}'.format(header['calculated_checksum']))


def handle_monitor_state_event_factory(command: str, only_interesting: bool) \
        -> Callable[[Dict[str, Union[str, int, bool]], Dict[str, Union[str, int, bool]]], None]:
    """
    Return a Callable suitable to be a callback function for Charger.monitor_state.

    :param only_interesting: Only run command if a human-readable message is available. Useful for
    instant messaging.
    :param command: Command to call in shell if something happened.
    """
    from subprocess import run
    from os import environ

    def handle_monitor_state_event(last_state: Dict[str, Union[str, int, bool]],
                                   event: Dict[str, Union[str, int, bool]]) -> None:
        """
        Handle an event by calling a command in the shell with an enriched environment.

        :param last_state: The state before the event occurred.
        :param event: The event dictionary, describing the reason as well as providing the
        packet indicating the change.
        """
        readable: str

        if event['_reason'] == 'mode id':
            readable = ('Channel {channel}: Mode changed to from {mode_was} to {mode_is}.'
                        .format(channel=event['channel'],
                                mode_is=event['mode string'],
                                mode_was=last_state['mode string']))
            if event['mode id'] in [4, 6, 8, 10, 12]:
                readable += ('\n{dimensions string} {chemistry string}: {mode string}\n'
                             '{energy} mWh, {resistance} Ω, {time} s, {temperature} °C'
                             .format(**event))
        elif event['_reason'] == 'dimensions id':
            readable = f'Channel {event["channel"]}: Dimensions changed to from ' \
                       f'{event["dimensions string"]} to {last_state["dimensions string"]}.'
        elif event['_reason'] == 'chemistry id':
            readable = f'Channel {event["channel"]}: Chemistry changed to from ' \
                       f'{last_state["chemistry string"]} to {event["chemistry string"]}.'
        elif event['_reason'] == 'periodic':
            voltage: float = event['charging voltage'] / 1000
            current: float = event['charging current'] / 1000
            power: float = event['power'] / 1000
            if event['dimensions id'] == 4:
                readable = 'Channel {channel}: Periodic update: empty'.format(**event)
            else:
                # charged, discharged, storaged [sic!], cycled, analyzed
                if event['mode id'] in [4, 6, 8, 10, 12]:
                    readable = ('Channel {channel}: Periodic update:\n'
                                '{dimensions string} {chemistry string}: {mode string}\n'
                                '{energy} mWh, {resistance} Ω, {time} s, {temperature} °C'
                                .format(**event))
                else:
                    readable = ('Channel {channel}: Periodic update:\n'
                                '{dimensions string} {chemistry string}: '
                                '{mode string} @ {progress} %\n'
                                '{voltage} V * {current} A = {div_power} W\n'
                                '{energy} mWh, {resistance} Ω, {time} s, {temperature} °C'
                                .format(**event, voltage=voltage, current=current,
                                        div_power=power))
        elif event['_reason'] == 'no channels':
            readable = "The charger doesn't have any channels. Bailing."
        elif event['_reason'] == 'channel id':
            readable = 'Channel found during initialization'
        else:
            readable = 'There is no reason for this event.'

        # Filter notifications without message for instant messaging
        if readable == "" and only_interesting:
            return

        env = environ.copy()
        env['HUMAN_READABLE'] = readable

        for k in event.keys():
            env[k.upper().replace(' ', '_')] = str(event[k])

        print(
            'Reason: {reason}. Calling {command}'.format(reason=event['_reason'], command=command))
        run(command, shell=True, env=env)

    return handle_monitor_state_event


def get_argument_parser() -> ArgumentParser:
    """Construct an appropriate ArgumentParser."""
    def hex_int(x: str) -> int:
        """
        Parse hex strings as if they were prefixed with `0x`.

        This is the common representation for USB IDs.
         :param x: Hex string without the leading `0x`.
        """
        return int(x, 16)

    parser = ArgumentParser(description='Tool to interact with ISDT C4, and A4 chargers, maybe '
                                        'compatible devices. It looks as if the protocol should '
                                        'be the same for most chargers.')
    parser.set_defaults(mode='')
    parser.add_argument('--pid', default=0x028a, type=hex_int,
                        help='The USB product ID to look for to connect to the charger. Defaults '
                             'is the model C4. Refer to lsusb(8). Has to be specified as a '
                             'non-prefixed hex number.')

    parser.add_argument('--vid', default=0x28e9, type=hex_int,
                        help='The USB vendor ID to look for to connect to the charger. Should be '
                             'OK to be left default for all possibly compatible chargers, '
                             'though.')

    parser.add_argument('--path', default='', type=str,
                        help='The platform specific hid path, only needed to distinguish '
                             'multiple chargers. Overrides --vid, and --pid')

    parser.add_argument('--output', default='text', type=str,
                        choices=['text', 'json', 'csv', 'dict', 'raw'],
                        help='How the output should be formatted.')

    parser.add_argument('--debug', '-d', default=False, action='store_const', const=True,
                        help='Enables protocol debugging.')

    subparsers = parser.add_subparsers()
    metrics_parser = subparsers.add_parser('metrics',
                                           help='Get the metrics of the specified channels.')
    metrics_parser.add_argument('--channels', '-c', type=int, nargs='*', default=[0, 1, 2, 3],
                                help='What channels to get the metrics from. 0-indexed. Defaults '
                                     'to 0 1 2 3.')
    metrics_parser.add_argument('--interval', '-i', type=float, default=1.0,
                                help='The interval between two reports. Defaults to 1.')
    metrics_parser.add_argument('--count', '-n', type=int, default=1,
                                help='How many reports should be generated. Defaults to 1. 0 '
                                     'means unlimited.')
    metrics_parser.set_defaults(mode='metrics')

    version_parser = subparsers.add_parser('version', help='Identify the charger.')
    version_parser.set_defaults(mode='version')

    link_test_parser = subparsers.add_parser('link-test', help='Test the connection.')
    link_test_parser.set_defaults(mode='link-test')

    reboot_bl_parser = subparsers.add_parser('boot-loader',
                                             help='Reboots the charger from app into bootloader.')
    reboot_bl_parser.set_defaults(mode='boot-loader')

    reboot_app_parser = subparsers.add_parser('boot-app',
                                              help='Reboots the charger from '
                                                   'any mode to app mode.')
    reboot_app_parser.set_defaults(mode='boot-app')

    rename_parser = subparsers.add_parser('rename',
                                          help='Rename the device. '
                                               'This causes an immediate reboot.')
    rename_parser.add_argument('--name', '-n', type=str, required=True,
                               help='The device\'s new name. 0 to 8 characters.')
    rename_parser.set_defaults(mode='rename')

    sensors_parser = subparsers.add_parser('sensors',
                                           help='Displays a bank of sensors for most of which I '
                                                'have no idea what they mean.')
    sensors_parser.set_defaults(mode='sensors')

    raw_command_parser = subparsers.add_parser('raw-command',
                                               help='Sends a raw payload to the charger. '
                                                    'Never use this one.')
    raw_command_parser.add_argument('--i-know-this-one-breaks-things', required=True,
                                    action='store_const', const=True,
                                    help='I swear I don\'t blame anyone.')
    raw_command_parser.add_argument('--command', type=hex_int, nargs='*', required=True,
                                    help='The raw payload to send to the charger.')
    raw_command_parser.set_defaults(mode='raw-command')

    decrypt_parser = subparsers.add_parser('decrypt-fw', help='Decrypt a firmware image.')
    decrypt_parser.add_argument('--file', '-f', type=argparse.FileType('rb'), required=True,
                                help='Encrypted input file.')
    decrypt_parser.add_argument('--outfile', '-w', type=argparse.FileType('wb'), required=True,
                                help='The name of the output file. Will overwrite existing files.')
    decrypt_parser.set_defaults(mode='decrypt-fw')

    verify_parser = subparsers.add_parser('verify-fw',
                                          help='Verifies a firmware image against a charger.')
    verify_parser.add_argument('--file', '-f', type=argparse.FileType('rb'), required=True,
                               help='Encrypted input file.')
    verify_parser.set_defaults(mode='verify-fw')

    fw_info_parser = subparsers.add_parser('fw-info',
                                           help='Displays information about the image file.')
    fw_info_parser.add_argument('--file', '-f', type=argparse.FileType('rb'), required=True,
                                help='Encrypted input file.')
    fw_info_parser.set_defaults(mode='fw-info')

    serial_number_parser = subparsers.add_parser('serial',
                                                 help='Gets the serial number, e.g. the unique '
                                                      'device identifier of the MCU.')
    serial_number_parser.set_defaults(mode='serial')

    monitor_parser = subparsers.add_parser('monitor',
                                           help='Call the provided command using the shell on '
                                                'every interesting change of the charging state. '
                                                'Populates the environment.')
    monitor_parser.add_argument('--command', '-c', type=str, required=False, default='env',
                                help='Command to run using the shell. If empty, it defaults to a'
                                     ' command that outputs what happened.')
    monitor_parser.add_argument('--interval', '-i', type=float, required=False, default=1,
                                help='How often to poll the charger. Float. Default 0.1')
    monitor_parser.add_argument('--period', '-p', type=int, required=False, default=0,
                                help='Run the command even if nothing has changed every n times. '
                                     'Default is 0, i.e. never.')
    monitor_parser.add_argument('--human', '-f', action='store_const', required=False,
                                default=False, const=True,
                                help='Only run the command if there is a human-readable message '
                                     'available. Useful for messaging.')
    monitor_parser.set_defaults(mode='monitor')

    return parser


def main() -> None:
    """Setup argument parser, and run."""
    parser = get_argument_parser()
    a = parser.parse_args()

    # a = parser.parse_args('metrics --channels 1 3 --count 0'.split(' '))
    # a = parser.parse_args('--output raw link-test'.split(' '))
    # a = parser.parse_args(['--path',
    #                        'IOService:/AppleACPIPlatformExpert/PCI0@0/AppleACPIPCI/EHC1@1D/'
    #                        'EHC1@1d000000/PRT1@1d100000/IOUSBHostDevice@1d100000/'
    #                        'AppleUSB20InternalIntelHub@1d100000/PRT1@1d110000/'
    #                        'Keyboard Hub@1d110000/AppleUSB20KeyboardHub@1d110000/'
    #                        'AppleUSB20HubPort@1d111000/ISDTC4@1d111000/IOUSBHostInterface@0/'
    #                        'AppleUserUSBHostHIDDevice', 'version'])
    # a = parser.parse_args('metrics --channels 3 --count 0 --interval 2'.split(' '))
    # a = parser.parse_args('--output csv rename --name ä!'.split(' '))
    # a = parser.parse_args('raw-command --i-know-this-one-breaks-things'
    #                       ' --command de 01'.split(' '))
    # a = parser.parse_args('raw-command --i-know-this-one-breaks-things'
    #                       ' --command f0 ac'.split(' '))
    # a = parser.parse_args(
    #     'decrypt-fw --file /tmp/pycharm_project_398/Firmware.fwd '
    #     '-w /tmp/pycharm_project_398/test.dec'.split(' '))
    # a = parser.parse_args('verify-fw --file Firmware.fwd'.split(' '))
    # a = parser.parse_args('raw-command --i-know-this-one-breaks-things '
    #                       '--command ac 01 02 03 04 05 06'.split(' '))
    # a = parser.parse_args('fw-info -f Firmware.fwd'.split(' '))
    # a = parser.parse_args('--output raw raw-command --i-know-this-one-breaks-things '
    #                       '--command AC 01 02 03 04 05 06'
    #                       .split(' '))
    # a = parser.parse_args('decrypt-fw --file /Users/max/PycharmProjects/isdt/Firmware.fwd '
    #                       '-w /Users/max/PycharmProjects/isdt/C4.bin'.split(' '))
    # a = parser.parse_args('serial'.split(' '))
    # a = parser.parse_args(['monitor', '-c',
    #                        '[ "$_REASON" == "mode id" ] && telegram "$HUMAN_READABLE"'])

    isdttool.DEBUG_MODE = a.debug

    if a.mode == '':
        parser.print_usage()
        exit(1)
    elif a.mode == 'decrypt-fw':
        firmware_decrypt(a.file, a.outfile)
    elif a.mode == 'fw-info':
        print_firmware_info(a.file)
    else:
        charger = None
        try:
            if a.path == '':
                charger = get_device(product_id=a.pid, vendor_id=a.vid)
            else:
                charger = get_device(path=a.path)
        except OSError as exception:
            print('Could not open charger:', str(exception), file=sys.stderr)
            exit(255)

        if a.mode == 'metrics':
            display_metrics(charger, a.interval, a.count, a.channels, a.output)
        elif a.mode == 'version':
            display_version(charger, a.output)
        elif a.mode == 'link-test':
            display_link_test(charger, a.output)
        elif a.mode == 'boot-loader':
            reboot_to_boot_loader(charger, a.output)
        elif a.mode == 'boot-app':
            reboot_to_app(charger, a.output)
        elif a.mode == 'rename':
            rename_device(charger, a.name, a.output)
        elif a.mode == 'sensors':
            display_sensors(charger, a.output)
        elif a.mode == 'raw-command':
            write_raw_command(charger, a.command, a.output)
        elif a.mode == 'verify-fw':
            verify_firmware(charger, a.file, a.output)
        elif a.mode == 'serial':
            read_serial_number(charger, a.output)
        elif a.mode == 'monitor':
            monitor_state(charger, handle_monitor_state_event_factory(a.command, a.human),
                          a.interval,
                          None if a.period <= 0 else a.period)


def tool_entrypoint() -> None:
    """The sole reason for this is to wrap the main function for setup.py."""
    main()
