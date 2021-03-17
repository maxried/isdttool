# isdttool

[![Codacy Badge](https://app.codacy.com/project/badge/Grade/4fe6e14e24c84419889c7f7da9e683d9)](https://www.codacy.com/gh/maxried/isdttool/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=maxried/isdttool&amp;utm_campaign=Badge_Grade)

## Important Notes
This software is not sponsored by ISDT, or anyone else. It was created by observing the protocol between the updater, then the charger, and fuzzing the charger, and observing its behavior. Chargers are dangerous tools. You should never use them unattended. Batteries can leak, catch fire, etc. This tool comes with no warranties whatsoever. If bad things happen, I'm not responsible.

## Summary

`isdttool` is a utility to retrieve information such as the current charging status from ISDT chargers. It can output it as plain text, json, and csv, so it should be suitable for automation. Tested models are
  - ISDT C4
  - ISDT A4
  - DNT Smart PRO (which just is a rebranded ISDT C4 with old firmware)

It should be compatible with other chargers by ISDT, at least the ones that are not primarily for charging LiPo. E.g. N8, or N24 should be compatible, but it's unknown if models like P20, or D1 work. It requires a USB connection. ISDT chargers with firmware upgrade capability should at least be detectable by this tool.

## Installation

The only dependency is `hidapi`, which should be automatically installed if you use `pip` to install `isdttool`.

    pip install isdttool

## Usage

Most options are self-explanatory, and you should not be able to break your charger with this tool unless you voluntarily use the `raw-command` sub-command. Firmware upgrades are not supported right now, but you can have a look at firmware files, and test if a certain image is flashed to your charger.

Usage examples:

    # The metrics command shows you the status of the channels. If you call it with --output json, the output is much more verbose.
    $ isdttool metrics
    CH 0      charging:    NiMH    AA at  90 %, 27 °C,  1.430 V *  0.999 A,  80 Ohm, 13 s
    CH 1        idling:    auto empty at   0 %, 28 °C,  0.000 V *  0.000 A,   0 Ohm, 0 s
    CH 2        idling:    auto empty at   0 %, 28 °C,  0.000 V *  0.000 A,   0 Ohm, 0 s
    CH 3      charging:    NiMH    AA at  99 %, 27 °C,  1.425 V *  1.003 A,  43 Ohm, 2 s
    
    $ isdttool --output json metrics --channel 0
    [{"_type": "metrics", "_channel exists": true, "channel": 0, "mode id": 3, "mode string": "charging", "chemistry id": 9, "chemistry string": "NiMH", "dimensions id": 1, "dimensions string": "AA", "temperature": 29, "internal_temperature": 0, "progress": 96, "charging voltage": 1383, "charging current": 799, "resistance": 83, "power": 1228, "energy": 31, "capacity or peak voltage": 4985, "time": 62, "_malformed": false, "_measurement": 1}]
    
    # If you happen to run a command that is not supported by the charger in its current mode,
    # you get a message about that. You can disable this check with the `--debug`, `-d` flag.
    $ isdttool sensors                                                                                                                       [12:03:43]
    This command is currently not supported by the model "A4" in app mode.
    The command is supported in the following modes:
    Model "C4" in app mode
    
    
    $ isdttool version
    Model name: C4
    Hardware version 1.0.0.4
    Bootloader version 1.0.0.3
    OS/App version 1.1.0.16
    
    $ isdttool rename --name Test
    Device renamed, rebooting.
    
    $ isdttool fw-info -f Firmware.fwd
    Firmware Image Summary
    ----------------------
    Embedded Checksum:   0xe063dcf7
    Calculated Checksum: 0xe063dcf7
    Checksum OK
    
    $ isdttool boot-loader
    Rebooting to bootloader.
    $ isdttool verify-fw --file A4.bin
    The checksum matches the checksum of the image in flash.
    
    $ isdttool boot-app
    Rebooting to app.
    
    # This one might not be obvious. It runs the supplied command whenever a change in the charging status happens.
    # It sets some informative environment variables. If you call it without `--command`, `-c` parameter,
    # it defaults to `env` to show you what's going on.
    $ isdttool monitor --command '[ "$_REASON" = "mode id" -o "$_REASON" = "periodic" ] && telegram "$HUMAN_READABLE"'
    [...]
    
    # Serial returns the factory programmed serial number of the processor.
    # This is different from the serial number shown in the GUI of the C4, which is most likely a date code, while the
    # serial number of the processor is supposed to be random.
    $ isdttool serial
    Serial Number: 33c0011816666b0410324d3d
    
    
    # If you have multiple chargers attached you can specify the one you like to query using the `--path` parameter.
    $ isdttool --path "IOService:/AppleACPIPlatformExpert/PCI0@0/[...]" version
    Model name: A4
    Hardware version 1.2.0.0
    Bootloader version 1.0.0.1
    OS/App version 1.0.0.20
