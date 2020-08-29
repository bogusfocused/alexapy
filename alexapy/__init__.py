#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
try:
    from importlib_metadata import version
except ModuleNotFoundError:
    from importlib.metadata import version
from .alexaapi import AlexaAPI
from .alexalogin import AlexaLogin
from .alexawebsocket import WebsocketEchoClient
from .errors import (
    AlexapyConnectionError,
    AlexapyLoginCloseRequested,
    AlexapyLoginError,
)
from .helpers import hide_email, hide_serial, obfuscate

__version__ = version("alexapy")

__all__ = [
    "AlexaLogin",
    "AlexaAPI",
    "AlexapyConnectionError",
    "AlexapyLoginCloseRequested",
    "AlexapyLoginError",
    "WebsocketEchoClient",
    "hide_email",
    "hide_serial",
    "obfuscate",
    "__version__",
]
