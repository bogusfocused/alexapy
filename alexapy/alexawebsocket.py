#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
import json
import logging
import ssl
import time
from threading import Thread

import websocket

_LOGGER = logging.getLogger(__name__)
OPCODE_BINARY = 0x2


class WebsocketEchoClient(Thread):
    """WebSocket Client Class for Echo Devices."""

    def __init__(self, login, msg_callback):
        """Init for threading and WebSocket Connection."""
        url = ("wss://dp-gw-na-js.{}/?x-amz-device-type={}"
               "&x-amz-device-serial=").format(login.url,
                                               'ALEGCNGL9K0HM')
        Thread.__init__(self)
        self._session = login.session
        self._cookies = self._session.cookies.get_dict()
        cookies = ""
        for key, value in self._cookies.items():
            cookies += key + "=" + value + "; "
        cookies = "Cookie: " + cookies
        url += str(self._cookies['ubid-main'])
        url += "-" + str(int(time.time())) + "000"
        self.msg_callback = msg_callback
        websocket_ = websocket.WebSocketApp(url,
                                            on_message=self.on_message,
                                            on_error=self.on_error,
                                            on_close=self.on_close,
                                            on_open=self.on_open,
                                            header=[cookies])
        self.websocket = websocket_
        Thread(target=self.run).start()

    def run(self):
        """Start WebSocket Listener."""
        self.websocket.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def on_message(self, message):
        # pylint: disable=too-many-statements
        """Handle New Message."""
        _LOGGER.debug("Received WebSocket MSG.")
        msg = message.decode('utf-8')
        _LOGGER.debug("Received %s", message)
        message_obj = Message()
        message_obj.service = msg[-4:]
        idx = 0
        if message_obj.service == "FABE":
            message_obj.message_type = msg[:3]
            idx += 4
            message_obj.channel = msg[idx:idx+10]
            idx += 11
            message_obj.message_id = msg[idx:idx+10]
            idx += 11
            message_obj.more_flag = msg[idx:idx+1]
            idx += 2
            message_obj.seq = msg[idx:idx+10]
            idx += 11
            message_obj.checksum = msg[idx:idx+10]
            idx += 11
            # currently not used: long contentLength = readHex(data, idx, 10);
            idx += 11
            message_obj.content.message_type = msg[idx:idx+3]
            idx += 4

            if message_obj.channel == "0x00000361":
                _LOGGER.debug("Received ACK MSG for Registration.")
                if message_obj.content.message_type == "ACK":
                    length = int(msg[idx:idx+10], 16)
                    idx += 11
                    message_obj.content.protocol_version = msg[idx:idx+length]
                    idx += length + 1
                    length = int(msg[idx:idx+10], 16)
                    idx += 11
                    message_obj.content.connectionUUID = msg[idx:idx+length]
                    idx += length + 1
                    message_obj.content.established = msg[idx:idx+10]
                    idx += 11
                    message_obj.content.timestamp_ini = msg[idx:idx+18]
                    idx += 19
                    message_obj.content.timestamp_ack = msg[idx:idx+18]
                    idx += 19

            elif message_obj.channel == "0x00000362":
                _LOGGER.debug("Received Standard MSG.")
                if message_obj.content.message_type == "GWM":
                    message_obj.content.submessage_type = msg[idx:idx+3]
                    idx += 4
                    message_obj.content.channel = msg[idx:idx+10]
                    idx += 11

                    if message_obj.content.channel == "0x0000b479":
                        length = int(msg[idx:idx+10], 16)
                        idx += 11
                        message_obj.content.dest_id_urn = msg[idx:idx+length]
                        idx += length + 1
                        length = int(msg[idx:idx+10], 16)
                        idx += 11
                        id_data = msg[idx:idx+length]
                        idx += length + 1
                        id_data_elements = id_data.split(" ", 2)
                        message_obj.content.device_id_urn = id_data_elements[0]
                        payload = None
                        if len(id_data_elements) == 2:
                            payload = id_data_elements[1]
                        if payload is None:
                            payload = msg[idx:-4]
                        message_obj.content.payload = payload
                        message_obj.json_payload = json.loads(payload)
                        message_obj.json_payload['payload'] = json.loads(
                            message_obj.json_payload['payload'])
        self.msg_callback(message_obj)

    def on_error(self, error):
        # pylint: disable=no-self-use
        """Handle WebSocket Error."""
        _LOGGER.error("WebSocket Error %s", error)

    def on_close(self):
        """Handle WebSocket Close."""
        _LOGGER.debug("WebSocket Connection Closed.")
        self.websocket.close()

    def on_open(self):
        """Handle WebSocket Open."""
        _LOGGER.debug("Initating Handshake.")
        self.websocket.send("0x99d4f71a 0x0000001d A:HTUNE", OPCODE_BINARY)
        time.sleep(1)
        self.websocket.send(self._encode_ws_handshake(), OPCODE_BINARY)
        time.sleep(1)
        self.websocket.send(self._encode_gw_handshake(), OPCODE_BINARY)
        time.sleep(1)
        self.websocket.send(self._encode_gw_register(), OPCODE_BINARY)

    def _encode_ws_handshake(self):
        # pylint: disable=no-self-use
        _LOGGER.debug("Encoding WebSocket Handshake MSG.")
        msg = "0xa6f6a951 "
        msg += "0x0000009c "
        msg += "{\"protocolName\":\"A:H\",\"parameters\":"
        msg += "{\"AlphaProtocolHandler.receiveWindowSize\":\"16\",\""
        msg += "AlphaProtocolHandler.maxFragmentSize\":\"16000\"}}TUNE"
        return msg

    def _encode_gw_handshake(self):
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
        return msg

    def _encode_gw_register(self):
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
        msg += "{\"command\":\"REGISTER_CONNECTION\"}"  # Message UUID
        msg += "FABE"
        return msg


class Content:
    # pylint: disable=too-few-public-methods, too-many-instance-attributes
    """Content Data Class."""

    def __init__(self):
        """Init for data."""
        self.message_type = ""
        self.protocol_version = ""
        self.connection_uuid = ""
        self.established = 0
        self.timestamp_ini = 0
        self.timestamp_ack = 0
        self.submessage_type = ""
        self.channel = 0
        self.dest_id_urn = ""
        self.device_id_urn = ""
        self.payload = ""
        self.payload_data = bytearray()


class Message:
    # pylint: disable=too-few-public-methods, too-many-instance-attributes
    """Message Data Class."""

    def __init__(self):
        """Init for data."""
        self.service = ""
        self.content = Content()
        self.content_tune = ""
        self.message_type = ""
        self.channel = 0
        self.checksum = 0
        self.message_id = 0
        self.more_flag = ""
        self.seq = 0
        self.json_payload = None
