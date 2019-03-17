#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
from .alexalogin import AlexaLogin
from .alexaapi import AlexaAPI
from .alexawebsocket import WebsocketEchoClient
from .__version__ import __version__

__all__ = ['AlexaLogin', 'AlexaAPI', 'WebsocketEchoClient', '__version__']
