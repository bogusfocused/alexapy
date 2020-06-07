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
from asyncio import CancelledError
from json import JSONDecodeError

from aiohttp import ClientConnectionError

from .const import EXCEPTION_TEMPLATE
from .errors import AlexapyConnectionError, AlexapyLoginError

_LOGGER = logging.getLogger(__name__)


def hide_email(email):
    """Obfuscate email."""
    part = email.split("@")
    return "{}{}{}@{}{}{}".format(
        part[0][0],
        "*" * (len(part[0]) - 2),
        part[0][-1],
        part[1][0],
        "*" * (len(part[1]) - 2),
        part[1][-1],
    )


def hide_serial(item):
    """Obfuscate serial."""
    if item is None:
        return ""
    if isinstance(item, dict):
        response = item.copy()
        for key, value in item.items():
            if isinstance(value, (dict, list)) or key in [
                "deviceSerialNumber",
                "serialNumber",
                "destinationUserId",
            ]:
                response[key] = hide_serial(value)
    elif isinstance(item, str):
        response = "{}{}{}".format(item[0], "*" * (len(item) - 4), item[-3:])
    elif isinstance(item, list):
        response = []
        for list_item in item:
            if isinstance(list_item, dict):
                response.append(hide_serial(list_item))
            else:
                response.append(list_item)
    return response


def _catch_all_exceptions(func):
    # pylint: disable=import-outside-toplevel
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except (ClientConnectionError, KeyError) as ex:
            _LOGGER.error(
                "%s.%s(%s, %s): A connection error occured: %s",
                func.__module__[func.__module__.find(".") + 1 :],
                func.__name__,
                args,
                kwargs,
                EXCEPTION_TEMPLATE.format(type(ex).__name__, ex.args),
            )
            raise AlexapyConnectionError
        except (JSONDecodeError) as ex:
            _LOGGER.error(
                "%s.%s(%s, %s): A login error occured: %s",
                func.__module__[func.__module__.find(".") + 1 :],
                func.__name__,
                args,
                kwargs,
                EXCEPTION_TEMPLATE.format(type(ex).__name__, ex.args),
            )
            raise AlexapyLoginError
        except CancelledError as ex:  # pylint: disable=broad-except
            _LOGGER.warning(
                "%s.%s(%s, %s): Timeout error occured accessing AlexaAPI: %s",
                func.__module__[func.__module__.find(".") + 1 :],
                func.__name__,
                args,
                kwargs,
                EXCEPTION_TEMPLATE.format(type(ex).__name__, ex.args),
            )
            return None
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error(
                "%s.%s(%s, %s): An error occured accessing AlexaAPI: %s",
                func.__module__[func.__module__.find(".") + 1 :],
                func.__name__,
                args,
                kwargs,
                EXCEPTION_TEMPLATE.format(type(ex).__name__, ex.args),
            )
            raise
            # return None

    return wrapper
