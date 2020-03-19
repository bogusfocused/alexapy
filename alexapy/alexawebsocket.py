#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
import asyncio
import json
import logging
import time
from typing import (
    Any,
    Callable,  # noqa pylint: disable=unused-import
    Coroutine,
    Dict,
    List,
    Text,
    Union,
    cast,
)

import aiohttp

from .alexalogin import AlexaLogin  # noqa pylint

_LOGGER = logging.getLogger(__name__)


class Content:
    # pylint: disable=too-few-public-methods, too-many-instance-attributes
    """Content Data Class."""

    def __init__(self) -> None:
        """Init for data."""
        self.message_type: Text = ""
        self.protocol_version: Text = ""
        self.connection_uuid: Text = ""
        self.established: int = 0
        self.timestamp_ini: int = 0
        self.timestamp_ack: int = 0
        self.submessage_type: Text = ""
        self.channel: int = 0
        self.dest_id_urn: Text = ""
        self.device_id_urn: Text = ""
        self.payload: Text = ""
        self.payload_data: bytearray = bytearray()


class Message:
    # pylint: disable=too-few-public-methods, too-many-instance-attributes
    """Message Data Class."""

    def __init__(self) -> None:
        """Init for data."""
        self.service: Text = ""
        self.content: Content = Content()
        self.content_tune: Text = ""
        self.message_type: Text = ""
        self.channel: int = 0
        self.checksum: int = 0
        self.message_id: int = 0
        self.more_flag: Text = ""
        self.seq: int = 0
        self.json_payload: Dict[Text, Union[Text, Dict[Text, Text]]] = {}


class WebsocketEchoClient:
    # pylint: disable=too-many-instance-attributes
    """WebSocket Client Class for Echo Devices.

    Based on code from openHAB:
    https://github.com/openhab/openhab2-addons/blob/master/addons/binding/org.openhab.binding.amazonechocontrol/src/main/java/org/openhab/binding/amazonechocontrol/internal/WebSocketConnection.java
    which is further based on:
    https://github.com/Apollon77/alexa-remote/blob/master/alexa-wsmqtt.js
    """

    def __init__(
        self,
        login: AlexaLogin,
        msg_callback: Callable[[Message], Coroutine[Any, Any, None]],
        open_callback: Callable[[], Coroutine[Any, Any, None]],
        close_callback: Callable[[], Coroutine[Any, Any, None]],
        error_callback: Callable[[Text], Coroutine[Any, Any, None]],
    ) -> None:
        # pylint: disable=too-many-arguments
        """Init for threading and WebSocket Connection."""
        if login.url.lower() == "amazon.com":
            subdomain = "dp-gw-na-js"  # type: Text
        else:
            subdomain = "dp-gw-na"
        url = ("wss://{}.{}/?x-amz-device-type={}" "&x-amz-device-serial=").format(
            subdomain, login.url, "ALEGCNGL9K0HM"
        )
        assert login.session is not None
        self._session = login.session
        self._cookies: Dict[Text, Text] = login._cookies if login._cookies else {}
        self._headers = login._headers
        self._ssl = login._ssl
        cookies = ""  # type: Text
        assert self._cookies is not None
        for key, value in self._cookies.items():
            cookies += "{}={}; ".format(key, value)
        self._headers["Cookie"] = cookies
        # the old websocket-client auto populates origin, which
        # aiohttp does not and is necessary for Amazon to accept a login
        self._headers["Origin"] = "https://alexa." + login.url
        url_array: List[Text] = login.url.split(".")
        ubid_id: Text = f"ubid-acb{url_array[len(url_array)-1]}"
        if ubid_id in self._cookies:
            url += str(self._cookies[ubid_id])
        elif "ubid-main" in self._cookies:
            url += str(self._cookies["ubid-main"])
        else:
            _LOGGER.warning(
                "Websocket is missing ubid-main and %s cookies;"
                " please report this if anything isn't working.",
                ubid_id,
            )
        url += "-" + str(int(time.time())) + "000"
        # url = "ws://localhost:8080/ws"
        self.open_callback: Callable[[], Coroutine[Any, Any, None]] = open_callback
        self.msg_callback: Callable[[Message], Coroutine[Any, Any, None]] = msg_callback
        self.close_callback: Callable[[], Coroutine[Any, Any, None]] = close_callback
        self.error_callback: Callable[
            [Text], Coroutine[Any, Any, None]
        ] = error_callback
        self._wsurl: Text = url
        self.websocket: aiohttp.ClientWebSocketResponse
        self._loop: asyncio.AbstractEventLoop

    async def async_run(self) -> None:
        """Start Async WebSocket Listener."""
        _LOGGER.debug("Connecting to %s with %s", self._wsurl, self._headers)
        self.websocket = await self._session.ws_connect(
            self._wsurl, headers=self._headers, heartbeat=180, ssl=self._ssl
        )
        loop = asyncio.get_event_loop()
        self._loop = loop
        task = loop.create_task(self.process_messages())
        task.add_done_callback(self.on_close)
        await self.async_on_open()

    async def process_messages(self) -> None:
        """Start Async WebSocket Listener."""
        _LOGGER.debug("Starting message parsing loop.")
        async for msg in self.websocket:
            # _LOGGER.debug("msg: %s", msg, extra=)
            if msg.type == aiohttp.WSMsgType.BINARY:
                await self.on_message(cast(bytes, msg.data))
            elif msg.type == aiohttp.WSMsgType.ERROR:
                self.on_error("WSMsgType error")
                break

    async def on_message(self, message: bytes) -> None:
        # pylint: disable=too-many-statements
        """Handle New Message."""
        msg: Text = message.decode("utf-8")
        _LOGGER.debug("Received WebSocket: %s", msg)
        message_obj: Message = Message()
        message_obj.service = msg[-4:]
        idx = 0  # type: int
        if message_obj.service == "FABE":
            message_obj.message_type = msg[:3]
            idx += 4
            message_obj.channel = int(msg[idx : idx + 10], 16)
            idx += 11
            message_obj.message_id = int(msg[idx : idx + 10], 16)
            idx += 11
            message_obj.more_flag = msg[idx : idx + 1]
            idx += 2
            message_obj.seq = int(msg[idx : idx + 10], 16)
            idx += 11
            message_obj.checksum = int(msg[idx : idx + 10], 16)
            idx += 11
            # currently not used: long contentLength = readHex(data, idx, 10);
            idx += 11
            message_obj.content.message_type = msg[idx : idx + 3]
            idx += 4

            if message_obj.channel == 0x00000361:
                _LOGGER.debug("Received ACK MSG for Registration.")
                if message_obj.content.message_type == "ACK":
                    length = int(msg[idx : idx + 10], 16)
                    idx += 11
                    message_obj.content.protocol_version = msg[idx : idx + length]
                    idx += length + 1
                    length = int(msg[idx : idx + 10], 16)
                    idx += 11
                    message_obj.content.connection_uuid = msg[idx : idx + length]
                    idx += length + 1
                    message_obj.content.established = int(msg[idx : idx + 10], 16)
                    idx += 11
                    message_obj.content.timestamp_ini = int(msg[idx : idx + 18], 16)
                    idx += 19
                    message_obj.content.timestamp_ack = int(msg[idx : idx + 18], 16)
                    idx += 19

            elif message_obj.channel == 0x00000362:
                _LOGGER.debug("Received Standard MSG.")
                if message_obj.content.message_type == "GWM":
                    message_obj.content.submessage_type = msg[idx : idx + 3]
                    idx += 4
                    message_obj.content.channel = int(msg[idx : idx + 10], 16)
                    idx += 11

                    if message_obj.content.channel == 0x0000B479:
                        length = int(msg[idx : idx + 10], 16)
                        idx += 11
                        message_obj.content.dest_id_urn = msg[idx : idx + length]
                        idx += length + 1
                        length = int(msg[idx : idx + 10], 16)
                        idx += 11
                        id_data = msg[idx : idx + length]
                        idx += length + 1
                        id_data_elements = id_data.split(" ", 2)
                        message_obj.content.device_id_urn = id_data_elements[0]
                        payload = None
                        if len(id_data_elements) == 2:
                            payload = id_data_elements[1]
                        if payload is None:
                            payload = msg[idx:-4]
                        message_obj.content.payload = payload
                        message_obj.json_payload = json.loads(str(payload))
                        (message_obj.json_payload["payload"]) = json.loads(
                            (
                                message_obj.json_payload[  # type: ignore
                                    "payload"
                                ]
                            )
                        )
            await self.msg_callback(message_obj)

    def on_error(self, error: Text = "Unspecified") -> None:
        """Handle WebSocket Error."""
        _LOGGER.error("WebSocket Error: %s", error)
        asyncio.run_coroutine_threadsafe(self.error_callback(error), self._loop)

    def on_close(self, future="") -> None:
        """Handle WebSocket Close."""
        exception_ = self.websocket.exception()
        if exception_:
            self.on_error(str(type(exception_)))
        _LOGGER.debug("WebSocket Connection Closed. %s", future)
        asyncio.run_coroutine_threadsafe(self.close_callback(), self._loop)

    async def async_on_open(self) -> None:
        """Handle Async WebSocket Open."""
        _LOGGER.debug("Initating Async Handshake.")
        await self.websocket.send_bytes(bytes("0x99d4f71a 0x0000001d A:HTUNE", "utf-8"))
        await asyncio.sleep(0.1)
        await self.websocket.send_bytes(self._encode_ws_handshake())
        await asyncio.sleep(0.1)
        await self.websocket.send_bytes(self._encode_gw_handshake())
        await asyncio.sleep(0.1)
        await self.websocket.send_bytes(self._encode_gw_register())
        await asyncio.sleep(0.1)
        await self.websocket.send_bytes(self._encode_ping())
        await asyncio.sleep(0.5)
        if not self.websocket.closed:
            await self.open_callback()

    def _encode_ws_handshake(self) -> bytes:
        # pylint: disable=no-self-use
        _LOGGER.debug("Encoding WebSocket Handshake MSG.")
        msg = "0xa6f6a951 "
        msg += "0x0000009c "
        msg += '{"protocolName":"A:H","parameters":'
        msg += '{"AlphaProtocolHandler.receiveWindowSize":"16","'
        msg += 'AlphaProtocolHandler.maxFragmentSize":"16000"}}TUNE'
        return bytes(msg, "utf-8")

    def _encode_gw_handshake(self) -> bytes:
        # pylint: disable=no-self-use
        _LOGGER.debug("Encoding Gateway Handshake MSG.")
        msg = "MSG 0x00000361 "  # MSG channel
        msg += "0x360da09c f 0x00000001 "  # Message number with no cont
        msg += "0x019f0778 "  # Checksum
        msg += "0x0000009b "  # Content Length
        msg += "INI 0x00000003 1.0 0x00000024 "  # Message content
        msg += "01e09e62-f504-476c-85c8-9c97c8da26ed "  # Message UUID
        msg += "0x0000016978ff598c "  # Hex encoded timestamp
        msg += "END FABE"
        return bytes(msg, "utf-8")

    def _encode_gw_register(self) -> bytes:
        # pylint: disable=no-self-use
        _LOGGER.debug("Encoding Gateway Register MSG.")
        msg = "MSG 0x00000362 "  # MSG channel
        msg += "0x33667875 f 0x00000001 "  # Message number with no cont
        msg += "0xfd0a5afa "  # Checksum
        msg += "0x00000109 "  # Content Length
        msg += "GWM MSG 0x0000b479 0x0000003b "  # Message content
        msg += "urn:tcomm-endpoint:device:deviceType:0:deviceSerialNumber:0 "
        msg += "0x00000041 "
        msg += "urn:tcomm-endpoint:service:serviceName:"
        msg += "DeeWebsiteMessagingService "
        msg += '{"command":"REGISTER_CONNECTION"}'  # Message UUID
        msg += "FABE"
        return bytes(msg, "utf-8")

    def _encode_ping(self) -> bytes:
        # pylint: disable=no-self-use
        _LOGGER.debug("Encoding PING.")
        msg = "MSG 0x00000065 "  # MSG channel
        msg += "0x0e414e47 f 0x00000001 "  # Message number with no cont
        msg += "0xbc2fbb5f "  # Checksum
        msg += "0x00000062 "  # Content Length
        msg += "PIN30"  # Message content
        msg += "FABE"
        return bytes(msg, "utf-8")
        # MSG 0x00000065 0x0e414e47 f 0x00000001 0xbc2fbb5f 0x00000062 PIN" + 30 + "FABE"
