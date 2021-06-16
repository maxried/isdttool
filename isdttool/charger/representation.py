#!/usr/bin/env python3
# coding=utf-8

"""These functions parse packets after they have been received from the charger."""
from collections import defaultdict
from struct import unpack_from
from typing import Tuple, Optional, Union, Dict, Any


def parse_packet(packet: bytearray, model: Optional[str]) -> \
        Dict[str, Union[str, int, bool]]:
    """
    This function returns a dict which corresponds to the packet. Might be wrong sometimes.
    :param packet: The payload as retrieved by read_packet
    :param model: Different models have different meanings of some fields.
    Specify either 'A4', 'C4', 'C4EVO', or 'Q8'. If None, ignore.
    :return: A dict with self explaining keys.
    """
    mode_strings = defaultdict(lambda: 'unknown', {})
    chemistry_strings = defaultdict(lambda: 'unknown', {})
    dimension_strings = defaultdict(lambda: 'unknown', {})
    if model in ['A4', 'C4']:
        mode_strings.update(
            {0: 'idling', 1: 'waiting', 2: 'reversed', 3: 'charging', 4: 'charged',
             5: 'discharging', 6: 'discharged', 7: 'storage', 8: 'storage done',
             9: 'cycling', 10: 'cycling done', 11: 'analysis', 12: 'analysis done'})

        # ID 4 seems to be unused.
        # NiMH!!! (6) are overcharged Ni cell. Set to NiMH, and insert a Li-Ion to show up.
        # Eneloop (7) doesn't seem as if it is any different from NiMH,
        # maybe has different Delta-V.
        chemistry_strings.update({
            0: 'auto', 1: 'LiHv', 2: 'Li-Ion', 3: 'LiPO4', 5: 'NiZn', 6: 'NiMH!!!', 7: 'Eneloop',
            8: 'NiCd', 9: 'NiMH'
        })

        if model == 'A4':
            dimension_strings[0] = 'AA(A)'
        elif model == 'C4':
            dimension_strings.update({0: 'AAA', 1: 'AA', 2: '18650', 3: '26650', 4: 'empty'})
    elif model in ['C4EVO']:
        # 'Cut off!!' is displayed on some errors like selecting NiMH for a Li-Ion thus making
        # the charger detect a far too high cell voltage. You can also get it when you frequently
        # disconnect, and reinsert a battery so quickly that it won't interrupt the charging. You
        # then also get an "UnKnown Error! 0x400" on the display. What about 14, and 16?
        # Firmware suggests some mode strings ("Charge State"?),
        # e.g. "csBattUnload" (empty slot), "csAnalysising" (analysing), but also something like
        # "tsTrickleChging", and also talks about balancing. Maybe this charger shares firmware
        # parts with some of their LiIon chargers.
        mode_strings.update(
            {0: 'idling', 1: 'waiting', 2: 'reversed', 3: 'charging', 4: 'charged',
             5: 'discharging', 6: 'discharged', 7: 'storage', 8: 'storage done',
             9: 'cycling', 10: 'cycling done', 11: 'analysis', 12: 'analysis done',
             13: 'activate', 15: 'destroy', 17: 'Cut off'})

        # C4EVO doesn't have Eneloop, and NiCd anymore. No big deal though.
        chemistry_strings.update({0: 'LiHv', 1: 'LiIon', 2: 'LiFe', 3: 'NiZn', 4: 'NiMH'})
        # The C4EVO has no information about dimensions.
    elif model in ['Q8']:
        # I don't have a Q8, but got some metrics dumps in issue #2. Thanks for that.
        # Unfortunately, the Q8 isn't really verbose with this opcode. There might be more, but
        # this would require hands-on testing. 
        mode_strings.update({3: 'charging'})
        chemistry_strings.update({9: 'LiIon'})
    elif model == 'ignore':
        pass  # Everything will be unknown then.
    else:
        raise ValueError(f'Model {model} is not supported.')

    result: Dict[str, Union[str, int, bool]] = dict()

    if packet[0] == 0x01:
        result['_type'] = 'link test'
        if len(packet) == 4:
            # C4 has only a 4 byte response while in app, it misses the device model
            # C4EVO always misses the model but when in bl mode it indicates the mode...
            result['_malformed'] = False
            result['result'] = True
            result['inside boot loader'] = packet[1] == 0x91
        elif len(packet) == 10:  # C4 in BL mode as well as A4 in any mode has a 10 byte response
            result['_malformed'] = False
            result['result'] = True
            result['inside boot loader'] = packet[1] == 0
            result['model'] = packet[2:].decode('ascii').rstrip('\x00')
        else:
            result['_malformed'] = True
    elif packet[0] == 0x03:
        result['_type'] = 'voltage-test-mode'
        result['_malformed'] = False
    elif packet[0] == 0xe1:  # Device information
        result['_type'] = 'device information'
        if len(packet) != 31 and len(packet) != 29 and len(packet) != 39:
            result['_malformed'] = True
        else:
            result['hw version'] = '{}.{}.{}.{}'.format(
                int(packet[9]), int(packet[10]), int(packet[11]), int(packet[12]))
            result['bl version'] = '{}.{}.{}.{}'.format(
                int(packet[13]), int(packet[14]), int(packet[15]), int(packet[16]))
            result['app version'] = '{}.{}.{}.{}'.format(
                int(packet[17]), int(packet[18]), int(packet[19]), int(packet[20]))
            result['model name'] = packet[21:31].decode('ascii').rstrip('\x00')

            if len(packet) == 39:
                # This is a total guess.
                # These are some of the last bytes of the BL section in flash.
                result['loader build time?'] = '20{:02d}-{:02d}-{:02d} {:02d}:{:02d}'.format(
                    *unpack_from('5B', packet, 0x21))

            result['_malformed'] = False
    elif packet[0] == 0xf1:
        result['_type'] = 'reboot to boot loader'
        if len(packet) != 2:
            result['_malformed'] = True
        else:
            if packet[1] == 0x00:
                result['rebooting'] = True
                result['next stop'] = 'boot loader'
                result['_malformed'] = False
            elif packet[1] == 0x02:
                result['rebooting'] = False
                result['_malformed'] = False
            else:
                result['_malformed'] = True
    elif packet[0] == 0xc1:
        result['_type'] = 'rename device'
        if len(packet) != 2:
            result['_malformed'] = True
        else:
            result['renamed'] = True
            result['rebooting'] = True
            result['next stop'] = 'app'
            result['_malformed'] = False
    elif packet[0] == 0xc9:
        result['_type'] = 'serial number'
        if len(packet) != 13:
            result['_malformed'] = True
        else:
            result['_malformed'] = False
            result['serial number'] = bytes(packet[1:]).hex()
    elif packet[0] == 0xfd:
        result['_type'] = 'reboot to app'
        if len(packet) != 2 and len(packet) != 1:
            result['_malformed'] = True
        else:
            result['rebooting'] = True
            result['next stop'] = 'app'
            result['_malformed'] = False
            result['coming from'] = ('boot loader' if len(packet) == 1 else 'app')
    elif packet[0] == 0xdf:
        result['_type'] = 'metrics'
        if len(packet) == 1:
            result['_channel exists'] = False
            result['_malformed'] = False
        elif len(packet) != 0x1a:
            result['_malformed'] = True
        else:
            # Unfortunately, it seems as if the values on the chargers GUI are ceil-rounded,
            # whereas the transmitted values are floor-rounded. This can causes discrepancies
            # between the values shown for the temperature, and resistance.

            result['_channel exists'] = True

            stats = unpack_from('<BBBBBBBhhHhhiI', packet, 1)
            result['channel'] = stats[0]

            result['mode id'] = stats[1]
            result['mode string'] = mode_strings[stats[1]]

            result['chemistry id'] = stats[2]
            result['chemistry string'] = chemistry_strings[stats[2]]

            result['dimensions id'] = stats[3]
            result['dimensions string'] = dimension_strings[stats[3]]

            result['temperature'] = stats[4]
            result['internal_temperature'] = stats[5]

            # Not 100 % sure about that. C4's fan turns on if > int(55.5), turns off if < int(
            # 47.5), or turns off if there is no charge flowing, e.g. all batteries are removed,
            # or put in waiting. Maybe it also stops when all batteries are charged,
            # but I didn't test. Unfortunately the temperature is not visible in GUI, and it is
            # only sent as integers. But the value range seems appropriate for a Celsius
            # temperature for a charging MOSFET. ISDT manufactures Lithium chargers, so it also
            # make perfectly sense to measure temperatures exactly. The fan seems to be
            # temperature driven, but only on, or off. Additionally, it is transmitted next to
            # the cell temperature.

            result['progress'] = stats[6]

            result['charging voltage'] = stats[7]
            result['charging current'] = stats[8]
            result['resistance'] = stats[9]
            result['power'] = stats[10]
            result['energy'] = stats[11]
            result['capacity or peak voltage'] = stats[12]
            result['time'] = stats[13]

            result['_malformed'] = False
    elif packet[0] == 0xf7:
        result['_type'] = 'app checksum'
        if len(packet) != 15:
            result['_malformed'] = True
        else:
            result['checksum matches'] = (packet[2] == 0x00)
            result['_malformed'] = False
    elif packet[0] == 0xf9:
        result['_type'] = 'sensors'
        if len(packet) != 0x1d:
            result['_malformed'] = True
        else:
            sensors: Tuple[Any] = \
                unpack_from('<xxxxxxHHHHHHHHBBBBBx', packet, 1)

            result['psu voltage'] = sensors[0]
            result['usb voltage'] = sensors[1]
            result['unknown voltage 1'] = sensors[2]
            result['unknown voltage 2'] = sensors[3]
            result['unknown voltage 3'] = sensors[4]
            result['unknown voltage 4'] = sensors[5]
            result['unknown voltage 5'] = sensors[6]
            result['unknown voltage 6'] = sensors[7]
            result['channel temperature 1'] = sensors[8]
            result['channel temperature 2'] = sensors[9]
            result['channel temperature 3'] = sensors[10]
            result['channel temperature 4'] = sensors[11]
            result['unknown temperature'] = sensors[12]

            result['_malformed'] = False
    elif packet[0] == 0xfb:
        result['_type'] = 'unknown voltages'
        if len(packet) != 19:
            result['_malformed'] = True
        else:
            result['_malformed'] = False

            voltages = unpack_from('<9H', packet, 1)
            result['unknown voltage 1'] = voltages[0]
            result['unknown voltage 2'] = voltages[1]
            result['unknown voltage 3'] = voltages[2]
            result['unknown voltage 4'] = voltages[3]
            result['unknown voltage 5'] = voltages[4]
            result['unknown voltage 6'] = voltages[5]
            result['unknown voltage 7'] = voltages[6]
            result['unknown voltage 8'] = voltages[7]
            result['unknown voltage 9'] = voltages[8]
    elif packet[0] == 0xe5:
        if model == 'C4EVO':
            result['_type'] = 'channel metrics'
            result['_malformed'] = False
            result['channel'], result['psu voltage'], result['charging voltage'], \
                result['current'], result['temperature'] = unpack_from('<BHHHxxB', packet, 1)
        else:
            result['_type'] = 'channel voltages'
            result['channel count'], result['psu voltage'], result['some 32 bit integer'], \
                result['total voltage'], result['another 32 bit integer'] = \
                unpack_from('<BHIHI', packet, 1)
            for index, voltage in \
                    enumerate(unpack_from(f'<{result["channel count"]}H', packet, 14)):
                result[f'channel voltage {index}'] = voltage
            result['_malformed'] = False
    else:
        result['_type'] = 'unknown'

    return result


def packet_to_str(response: Union[bytearray, Dict[str, Union[str, int, bool]]], model: str) -> str:
    """
    Convert a packet to a human readable string.
    :param response: The packet data as received by read_packet, or preparsed as dict.
    :param model: Different models have different meanings of some fields.
    :return: A human readable string.
    """
    result: Optional[str]
    packet: defaultdict[str, Union[str, int, bool]]

    if isinstance(response, bytearray):
        packet = defaultdict(lambda: 'n/a', parse_packet(response, model))
    elif isinstance(response, dict):
        packet = defaultdict(lambda: 'n/a', **response)
    else:
        raise ValueError()

    if packet['_type'] == 'link test':
        result = 'Link test ' + 'succeeded' if packet['result'] else 'failed'
        result += '\nCurrently running the ' + ('boot loader' if packet['inside boot loader'] else
                                                'app')
    elif packet['_type'] == 'device information':
        result = ('Model name: {}\n'
                  'Hardware version {}\n'
                  'Boot loader version {}\n'
                  'OS/App version {}').format(packet['model name'], packet['hw version'],
                                              packet['bl version'], packet['app version'])
    elif packet['_type'] == 'reboot to boot loader':
        result = 'Rebooting to boot loader.'
    elif packet['_type'] == 'rename device':
        result = 'Device renamed, rebooting.'
    elif packet['_type'] == 'reboot to app':
        result = 'Rebooting to app.'
    elif packet['_type'] == 'metrics':
        if packet['_channel exists']:
            voltage = packet['charging voltage'] / 1000
            current = packet['charging current'] / 1000
            result = ('CH {channel} {mode string:>13}: {chemistry string:>7} '
                      '{dimensions string:>5} at {progress:>3} %, {temperature:>2} °C, '
                      '{voltage:>6.3f} V * {current:>6.3f} A, '
                      '{resistance:>3d} Ohm, {time} s'
                      ).format(voltage=voltage, current=current, **packet)
        else:
            result = 'Channel does not exist.'
    elif packet['_type'] == 'sensors':
        result = ('Sensors:\n'
                  'PSU Voltage: {psu voltage} mV\n'
                  'USB Voltage: {usb voltage} mV\n'
                  'Unknown Voltage 1: {unknown voltage 1} mV\n'
                  'Unknown Voltage 2: {unknown voltage 2} mV\n'
                  'Unknown Voltage 3: {unknown voltage 3} mV\n'
                  'Unknown Voltage 4: {unknown voltage 4} mV\n'
                  'Unknown Voltage 5: {unknown voltage 5} mV\n'
                  'Unknown Voltage 6: {unknown voltage 6} mV\n'
                  'Channel Temperature 1: {channel temperature 1} °C\n'
                  'Channel Temperature 2: {channel temperature 2} °C\n'
                  'Channel Temperature 3: {channel temperature 3} °C\n'
                  'Channel Temperature 4: {channel temperature 4} °C\n'
                  'Unknown Temperature: {unknown temperature} °C\n').format(**packet)
    elif packet['_type'] == 'app checksum':
        if packet['checksum matches']:
            result = 'The checksum matches the checksum of the image in flash.'
        else:
            result = 'The checksum DOES NOT match the checksum of the image in flash.'
    elif packet['_type'] == 'serial number':
        result = 'Serial Number: ' + packet['serial number']
    elif packet['_type'] == 'unknown voltages':
        result = ('Voltages:\n'
                  'Unknown Voltage 1: {unknown voltage 1} mV\n'
                  'Unknown Voltage 2: {unknown voltage 2} mV\n'
                  'Unknown Voltage 3: {unknown voltage 3} mV\n'
                  'Unknown Voltage 4: {unknown voltage 4} mV\n'
                  'Unknown Voltage 5: {unknown voltage 5} mV\n'
                  'Unknown Voltage 6: {unknown voltage 6} mV\n'
                  'Unknown Voltage 7: {unknown voltage 7} mV\n'
                  'Unknown Voltage 8: {unknown voltage 8} mV\n').format(**packet)
    elif packet['_type'] == 'channel metrics':
        result = f'Channel: {packet["channel"]}\n' \
                 f'PSU Voltage: {packet["psu voltage"]} mV\n' \
                 f'Charging voltage: {packet["charging voltage"]} mV\n' \
                 f'Current: {packet["current"]} mA\n' \
                 f'Temperature: {packet["temperature"]} °C\n'
    elif packet['_type'] == 'channel voltages':
        result = f'Channel Count: {packet["channel count"]}\n' \
                 f'PSU Voltage: {packet["psu voltage"]} mV\n'
        for i in range(packet['channel count']):
            result += f'Channel {i} Voltage: {packet[f"channel voltage {i}"]} mV\n'
    else:
        result = None

    if packet['_malformed']:
        return 'MALFORMED!\n' + (result if result is not None else 'Unknown packet type.')
    else:
        return result
