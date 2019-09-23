#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

Helpers.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
import logging

from aiohttp import ClientConnectionError

from .errors import AlexapyConnectionError

_LOGGER = logging.getLogger(__name__)


def _catch_all_exceptions(func):
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        template = ("An exception of type {0} occurred."
                    " Arguments:\n{1!r}")
        try:
            return func(*args, **kwargs)
        except ClientConnectionError as ex:
            message = template.format(type(ex).__name__, ex.args)
            _LOGGER.error("%s.%s: A connection error occured: %s",
                          func.__module__[func.__module__.find('.')+1:],
                          func.__name__,
                          message)
            raise AlexapyConnectionError
        except Exception as ex:  # pylint: disable=broad-except
            message = template.format(type(ex).__name__, ex.args)
            _LOGGER.error("%s.%s:An error occured accessing AlexaAPI: %s",
                          func.__module__[func.__module__.find('.')+1:],
                          func.__name__,
                          message)
            return None
    return wrapper
