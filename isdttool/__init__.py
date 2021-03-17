# coding=utf-8

"""
This is an implementation of the protocol spoken by ISDT chargers.

The way the protocol is
designed suggests that it might be the same for a number of those chargers, but this one was
reverse engineered using a ISDT C4, and a A4 charger. I assume that the measurements will come
out wrong for other models, but it should be easy to adopt. There are things in the protocol which
I didn't understand. You're welcome to help. A C4evo charger is already ordered.
"""

from .charger.charger import get_device, Charger

DEBUG_MODE = False

__all__ = ('get_device', 'Charger')


def set_debug(enabled: bool) -> None:
    """
    Enable, or disable the protocol debug mode.

    :param enabled: Knob direction
    """
    global DEBUG_MODE
    DEBUG_MODE = enabled
