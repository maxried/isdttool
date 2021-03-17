# coding=utf-8

"""Tools for reversing ISDT firmware files. Works for all tested chargers so far."""

from struct import unpack, error
from typing import BinaryIO, Tuple, Dict, Any, Optional
from io import BytesIO


def decrypt_firmware_image(encrypted: BinaryIO, output: BinaryIO) -> Dict[str, int]:
    """
    Decrypt the firmware image into output, and return the firmware header as a dict.

    :param encrypted: IO (aka file) where the firmware is stored
    :param output: IO (might also be something different than a file) to write the
    decrypted firmware to.
    :return: The firmware header
    """
    header: bytes = encrypted.read(32)

    try:
        unpacked_header: Tuple[Any] = unpack('<8I', header)
    except error:  # Thank you Mr Struct for such useful exception names.
        return {}

    encryption_key: int = unpacked_header[0]
    file_checksum: int = unpacked_header[1]
    app_storage_offset: int = unpacked_header[2]
    data_storage_offset: int = unpacked_header[3]
    app_size: int = unpacked_header[4]
    data_size: int = unpacked_header[5]
    initial_baud_rate: int = unpacked_header[6]
    fast_baud_rate: int = unpacked_header[7]

    key1: int = encryption_key
    key2: int = file_checksum

    calculated_checksum: int = 0
    read: bytes = encrypted.read(4)
    while len(read) >= 4:
        block, = unpack('<I', read)
        block ^= key2
        key2 = (key2 + key1) & 0xFFFFFFFF
        key2 ^= key1

        output.write(int.to_bytes(block, length=4, byteorder='little', signed=False))
        calculated_checksum = (calculated_checksum + block) & 0xFFFFFFFF
        read = encrypted.read(4)

    information_structure = dict()
    if output.seekable() and output.readable():
        unpacked_information_structure: Optional[Tuple] = None  # Large tuple...
        try:
            # Encryption done, now read the information structure inside the image:
            # As far as I can tell, the pointer to the info structure starts at 40.
            output.seek(40)
            pointer: int = int.from_bytes(output.read(4), byteorder='little',
                                          signed=False) - app_storage_offset
            # Seek into the file to where the structure is located
            output.seek(pointer)
            unpacked_information_structure = unpack('<I8s8b2I', output.read(28))
            # Rewind the tape after we read the structure.
            output.seek(0)
            information_structure['info_structure_pointer'] = pointer
        except (error, IOError):
            pass

        if unpacked_information_structure is not None:
            information_structure['magic'] = unpacked_information_structure[0]
            information_structure['model_name'] = unpacked_information_structure[1].rstrip(
                b'\x00').decode('ascii')
            information_structure['hw_version'] = '{}.{}.{}.{}'.format(
                unpacked_information_structure[2],
                unpacked_information_structure[3],
                unpacked_information_structure[4],
                unpacked_information_structure[5])
            information_structure['sw_version'] = '{}.{}.{}.{}'.format(
                unpacked_information_structure[6],
                unpacked_information_structure[7],
                unpacked_information_structure[8],
                unpacked_information_structure[9])
            information_structure['entrypoint'] = unpacked_information_structure[10]
            information_structure['app_image_size'] = unpacked_information_structure[11]

    return dict(embedded_checksum=file_checksum, calculated_checksum=calculated_checksum,
                app_storage_offset=app_storage_offset, data_storage_offset=data_storage_offset,
                app_size=app_size,
                data_size=data_size, initial_baud_rate=initial_baud_rate,
                fast_baud_rate=fast_baud_rate,
                **information_structure)


def print_firmware_info(file: BinaryIO) -> None:
    """
    Print out the header of an encrypted image file.

    :param file: the image to analyse.
    """
    decrypted_firmware = BytesIO()
    header: Dict[str, int] = decrypt_firmware_image(file, decrypted_firmware)

    checksum_matches = 'Checksum ' + 'OK ' if header['calculated_checksum'] == header[
        'embedded_checksum'] else 'wrong'

    print('Firmware Image Summary\n'
          '----------------------\n'
          'Embedded Checksum:   0x{embedded_checksum:x}\n'
          'Calculated Checksum: 0x{calculated_checksum:x}\n'
          '{checksum_matches}\n'
          '\n'
          'App Summary\n'
          '-----------\n'
          'App Storage Offset: 0x{app_storage_offset:x}\n'
          'App Size:           {app_size} bytes\n'
          '\n'
          'Data Summary\n'
          '------------\n'
          'Data Storage Offset: 0x{data_storage_offset:x}\n'
          'Data Size:           {data_size} bytes\n'
          '\n'
          'Flashing Summary\n'
          '----------------\n'
          'Initial Baud Rate: {initial_baud_rate}\n'
          'Fast Baud Rate:    {fast_baud_rate}'.format(**header,
                                                       checksum_matches=checksum_matches))
    print()
    try:
        print('Firmware Summary\n'
              '----------------\n'
              'Information Structure at 0x{info_structure_pointer:x}\n'
              'Magic:                   0x{magic:x}\n'
              'Model Name:              {model_name}\n'
              'Hardware Version:        {hw_version}\n'
              'Software Version:        {sw_version}\n'
              'Entrypoint:              0x{entrypoint:x}\n'
              'App Size:                {app_image_size} bytes'.format(**header))
    except (IOError, KeyError):
        print('Could not read firmware info table.')
