# ISDT USB Protocol

## Frame

The chargers don't have responses longer than 64 bytes as far as I know, so implementing only the first part of these findings are sufficient for reading responses. More than one frame only seems to be necessary for flashing the firmware image. The charger seems to be tolerant if your implementation violates the specs, though. The first byte of the packet data is always the opcode. Requests are always even, and responses are always odd. Also, they are always just the opcode of the request incremented by one, except for the retransmission opcode. The C4 handles packets without padding while the A4 stops responding. As of 2020-11-08, this prevents the macOS updater to work with the A4.  

### First Packet

    XX: 0x01: Request, 0x02: Response
    XX: Frame length, sometimes off by two. The bootloader, and the app seem to disagree.
    AA: Synchronization symbol. Starting here every 0xAA will be doubled, i.e. escaped so you can't confuse it with a synchronization symbol. It looks as if they didn't design this protocol for use with USB, but they just put a protocol meant for serial communication inside 64-byte-long USB packets.
    XX: Recipient: 0x12: Computer -> Charger, 0x21: Charger -> Computer
    XX: Packet size, escaped AA characters count as 1 byte.
    XX: Packet data
    XX: ...
    XX: 8 bit sum of the data, if it is the only packet
    XX: Padding to fill 64 bytes

### Subsequent packets

    XX: 0x01: Request, 0x02: Response
    XX: Frame length
    XX: Continuation of the packet data
    XX: ...
    XX: 8 bit sum of the data
    XX: Padding to fill 64 bytes

## Opcodes

### 0x00

Link test. Works in bootloader mode, and in app mode. If running in non-C4EVO bootloader mode, the packet will be longer, and it will contain the charger model name. Available in C4, C4EVO, and A4.

### 0x02

Channel voltage and current monitoring on the C4EVO in app mode.

### 0x04

C4EVO only, returns information about two memory locations.

### 0x08

C4EVO only, returns 6, if some memory address is set to 0x01, a 1, and the hardware version.

### 0x20

"App Data" commands. It seems as if there are devices which have some additional payload that comes with firmware images. As of July 2020, no downloadable firmware image contains such "App Data". It seems to be implemented in the official updater. It comes in two sub-commands, which are sent as the first parameter. They are implemented analogously to the firmware update commands. It's unsupported by both the A4 and C4 app as well as the bootloaders.

    0x05: Write App Data
    0x06: Checksum App Data

### 0xA0

Does something on C4EVO in App mode. Expects A5 C3 as parameters to unlock, followed by a parameter that has to be FF to do _something_. Nulls out PN until reboot. No operation on A4, C4.

### 0xA2, 0xA4

No operation. It doesn't even send a response. There is a code path for this opcode, but it does nothing, might be used in other firmware versions. Only _implemented_ in C4 app.

# 0xA6

Does something on C4EVO in App mode, no op on A4, C4.

# 0xA8

Does something on C4EVO in App mode, no op on A4, C4.

### 0xAA

Just echoes, maybe it does something more interesting on other chargers. Seems to take YY ZZ as input and returns YY ZZ DE on the C4 and YY ZZ 00 on the A4. Only available in app mode.

### 0xAC

This one sets the serial number. It takes 6 bytes as parameter, and then sets the serial number to: `{0:02d}{1:02d}{2:02d}{3:02d}{4:02d}{5:02d}-{:d}` where the last one is set using the 0xEE command, and is called 'UserId'. It does not use the standard packet format, and it returns a lot more information with unknown meaning. Seems to be a timestamp of the manufacturing date in the format YYMMDDhhmmss. This is only available on C4 in app mode.
e.g. 210311100000-00000
### 0xC0

Device rename, maximum 8 bytes. The encoding of the string is unknown, but it feels as if it's a UTF-8 subset. Sending `b'\xc0YourName'` sets the name, and reboots the charger immediately.

### 0xC2

Language configuration. There are two cases. If you send 3 bytes total:

`C2 5A XX` sets the available languages using a bit mask, and reboots to app again. Setting all bits to zero does
nothing. If the chosen language set is only bit 7, English will always be available. It once also set my device's name to _lish_. No clue.

    bit 0: English
    bit 1: Simplified Chinese
    bit 2: Traditional Chinese
    bit 3: Japanese
    bit 4: German
    bit 5: French
    bit 6: Spanish, Russian
    bit 7: unused

If you send 5 bytes total like `C2 5A A5 XX YY`, it does _something_ and returns a non-standard in addition to a well-formed packet.

### 0xC4

Only on C4EVO.

### 0xC8

Returns the unique device ID register burnt into the microcontroller. It has no semantic.

### 0xCE

Only on C4EVO. 

### 0xDE

This one is very interesting. It returns the measurements of the charging channels. Second byte is the 0-indexed channel number. Refer to the implementation for details.

### 0xE0

Device model and firmware version. Parameters don't change the packet. Refer to the implementation for details.

### 0xE2

No operation. It doesn't even send a response. There is code path for this opcode, but it does nothing, might be used in other firmware versions.

### 0xE4

Only on C4EVO. Takes a channel number as its argument. If it's larger than 5, it will be set to 0. It then returns information about the psu, and the channel.

### 0xE6

No operation. It doesn't even send a response. There is code path for this opcode, but it does nothing, might be used in other firmware versions.

### 0xE8

Echoes the first parameter byte XX, returning e9 XX YY 19 YY. YYYY are 2 bytes which are unchanged from the last response, because the code misses initializing them. 19 is always 19.

### 0xEA

Retransmit the last send buffer. Crashes the unit if it's sent as the first command after power on.

### 0xEC

EC 5A A5 YY just echoes edYY00. Might be something more interesting on other models.

### 0xEE

This one sets the 'UserId'. For my unit, it was 0 when it came from factory. See 0xAC for more details. It does not use the standard packet format, and it returns a lot more information with unknown meaning. Only implemented on C4, missing on A4.

### 0xF0

Reboots to bootloader. Only 0xAC as its parameter does something here. Available in C4 and A4. Returns F1 00 if the device actually reboots. On A4, it returns F1 02 if the device is charging and therefore refuses to reboot. Only these two return codes are possible.

### 0xF2

Erases firmware blocks. Found in the official updater. Didn't dare to send. Only works in bootloader mode.

### 0xF4

Writes firmware. Didn't dare to send. Found in the official updater. Didn't dare to send. Only works in bootloader mode. At least the A4 bootloader has precautions that prevent us from overwriting the bootloader. This should keep us safe.

### 0xF6

Verifies the checksum of the flash. Only works in bootloader mode. See implementation for details.

### 0xF8

Returns miscellaneous sensor information, containing PSU voltage, USB output voltage, some numbers that look like internal voltages and the temperature sensors. The meaning of the last one is unclear, might be the CPU?

### 0xFA

Voltage information for each channel. They come in pairs of two. One of them is the voltage during charging, and the other one is the actual current cell voltage. If a channel is empty, the ADC input is floating, and the read value is bogus. Unfortunately it seems as if there is an off-by-one, so voltage 1 is always 0, and the cell voltage of channel 4 is missing. If you insert a Lithium cell into a channel, the voltage as transmitted by the charger seems to be 1 V too low. It does not directly read from the ADCs, but it reads from memory. I can't see where this memory gets written.

### 0xFC

Reboots to App, needs 0xCA as parameter. When in app mode C4EVO also reboots when you just send FC, but it feels more like crashing as it doesn't confirm the reboot request. 

### 0xFE

Test mode stuff. Scary. Does a lot of weird things. Feels like breaking your device. Parameters I tested: `0x02` turns on the fan, and sometimes causes clicking noises if you send it multiple times, `0x03` crashes the device, `0x04` seems to change something regarding the channel controllers, i.e. setting some voltages, e.g. FE 04 02 causes internal temperature increase, `0x05` sets it into testing mode of which I have no clue if it's a good idea to be there, you stay in there until the test completes, `0x06` displays "Check".

## Boot Modes

There are two boot modes, maybe three if you can reach the DFU mode of the micro-controller somehow. The first mode is the app mode, which is the normal mode of operation. The second mode is the bootloader mode, which is either started by sending a specific opcode while in app mode, or by first plugging it into USB, and then connecting power afterwards, though the second mechanism might be model specific. If your in bootloader mode, the C4 beeps until it receives the first packet, even if it doesn't make sense. The two modes support different subset of commands.

## Supported Commands

### C4

       | _0 | _2 | _4 | _6 | _8 | _A | _C | _E |  
    ---|----|----|----|----|----|----|----|----|
    0_ | BA |    |    |    |    |    |    |    |
    1_ |    |    |    |    |    |    |    |    |
    2_ | ?  |    |    |    |    |    |    |    |
    3_ |    |    |    |    |    |    |    |    |
    4_ |    |    |    |    |    |    |    |    |
    5_ |    |    |    |    |    |    |    |    |
    6_ |    |    |    |    |    |    |    |    |
    7_ |    |    |    |    |    |    |    |    |
    8_ |    |    |    |    |    |    |    |    |
    9_ |    |    |    |    |    |    |    |    |
    A_ |  A |  A |  A |  A |  A |  A |  A |    |
    B_ |    |    |    |    |    |    |    |    |
    C_ |  A |  A |    |    |  A |    |    |    |
    D_ |    |    |    |    |    |    |    |  A |
    E_ | BA |  A |  A |  A |  A |  A |  A |  A |
    F_ |  A | B  | B  | B  |  A |  A | BA |  A |
    
    A: Supported in app mode
    B: Supported in boot loader mode
    ?: Unclear, might be supported in boot loader mode

### A4

       | _0 | _2 | _4 | _6 | _8 | _A | _C | _E |  
    ---|----|----|----|----|----|----|----|----|
    0_ | BA |    |    |    |    |    |    |    |
    1_ |    |    |    |    |    |    |    |    |
    2_ |    |    |    |    |    |    |    |    |
    3_ |    |    |    |    |    |    |    |    |
    4_ |    |    |    |    |    |    |    |    |
    5_ |    |    |    |    |    |    |    |    |
    6_ |    |    |    |    |    |    |    |    |
    7_ |    |    |    |    |    |    |    |    |
    8_ |    |    |    |    |    |    |    |    |
    9_ |    |    |    |    |    |    |    |    |
    A_ |  A |    |    |    |    |    |  A |    |
    B_ |    |    |    |    |    |    |    |    |
    C_ |    |    |    |    |  A |    |    |    |
    D_ |    |    |    |    |    |    |    |  A |
    E_ | BA |    |    |    |  A |  A |  A |  A |
    F_ | BA | B  | B  | B  |    |    | B  |  A |
    
    A: Supported in app mode
    B: Supported in boot loader mode


### C4EVO (incomplete)

       | _0 | _2 | _4 | _6 | _8 | _A | _C | _E |  
    ---|----|----|----|----|----|----|----|----|
    0_ | BA |  A |  A |    |  A |  A |    |    |
    1_ |    |    |    |    |    |    |    |    |
    2_ |    |    |    |    |    |    |    |    |
    3_ |    |    |    |    |    |    |    |    |
    4_ |    |    |    |    |    |    |    |    |
    5_ |    |    |    |    |    |    |    |    |
    6_ |    |    |    |    |    |    |    |    |
    7_ |    |    |    |    |    |    |    |    |
    8_ |    |    |    |    |    |    |    |    |
    9_ |    |    |    |    |    |    |    |    |
    A_ |    |    |    |    |    |    |    |    |
    B_ |    |    |    |    |    |    |    |    |
    C_ |    |    |    |    |    |    |    |    |
    D_ |    |    |    |    |    |    |    |    |
    E_ |    |    |    |    |    |    |    |    |
    F_ | BA |    |    |    |    |    |    |    |
    
    A: Supported in app mode
    B: Supported in boot loader mode


## Remarks

This is only about the ISDT USB protocol. The Bluetooth LE based protocol supported by newer chargers seems to work similar, but seems to have the opcodes increased by 1. This might be worth some further investigation.
