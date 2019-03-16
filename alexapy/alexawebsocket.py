#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
import websocket
from threading import Thread
import time
import ssl
import json
import logging

_LOGGER = logging.getLogger(__name__)
OPCODE_BINARY = 0x2


class WebSocket_EchoClient(Thread):
    """WebSocket Client Class for Echo Devices."""

    def __init__(self, login, url, msg_callback):
        """Init for threading and WebSocket Connection."""
        Thread.__init__(self)
        self._session = login.session
        self._cookies = self._session.cookies.get_dict()
        cookies = ""
        for cookie in self._cookies:
            cookies += cookies + "; "
        cookies = "Cookie: " + cookie
        self.msg_callback = msg_callback
        websocket.enableTrace(True)
        ws = websocket.WebSocketApp(url,
                                    on_message=lambda ws, msg: self.on_message(
                                        ws, msg),
                                    on_error=lambda ws, msg: self.on_error(
                                        ws, msg),
                                    on_close=lambda ws:     self.on_close(
                                        ws),
                                    on_open=lambda ws:     self.on_open(
                                        ws),
                                    header=[cookies])
        self.ws = ws

    def run(self):
        """Start WebSocket Listener."""
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def on_message(self, ws, message):
        """Handle New Message."""
        msg = message.decode('utf-8')
        message_obj = Message()
        message_obj.service = msg[-4:]
        idx = 0
        if message_obj.service == "FABE":
            message_obj.messageType = msg[:3]
            idx += 4
            message_obj.channel = msg[idx:idx+10]
            idx += 11
            message_obj.messageId = msg[idx:idx+10]
            idx += 11
            message_obj.moreFlag = msg[idx:idx+1]
            idx += 2
            message_obj.seq = msg[idx:idx+10]
            idx += 11
            message_obj.checksum = msg[idx:idx+10]
            idx += 11
            # currently not used: long contentLength = readHex(data, idx, 10);
            idx += 11
            message_obj.content.messageType = msg[idx:idx+3]
            idx += 4

            if message_obj.channel == "0x00000361":
                print("Gateway Handshake Messsage Received")
                if message_obj.content.messageType == "ACK":
                    print("Gateway Handsake Message Type: ACK")
                    length = int(msg[idx:idx+10], 16)
                    idx += 11
                    message_obj.content.protocolVersion = msg[idx:idx+length]
                    idx += length + 1
                    length = int(msg[idx:idx+10], 16)
                    idx += 11
                    message_obj.content.connectionUUID = msg[idx:idx+length]
                    idx += length + 1
                    message_obj.content.established = msg[idx:idx+10]
                    idx += 11
                    message_obj.content.timestampINI = msg[idx:idx+18]
                    idx += 19
                    message_obj.content.timestampACK = msg[idx:idx+18]
                    idx += 19

            elif message_obj.channel == "0x00000362":
                print("Gateway Message Received")
                if message_obj.content.messageType == "GWM":
                    print("Gateway Message Type: GWM")
                    message_obj.content.subMessageType = msg[idx:idx+3]
                    idx += 4
                    message_obj.content.channel = msg[idx:idx+10]
                    idx += 11

                    if message_obj.content.channel == "0x0000b479":
                        print("Message Contains DeeWebsiteMessage")
                        length = int(msg[idx:idx+10], 16)
                        idx += 11
                        message_obj.content.destIdUrn = msg[idx:idx+length]
                        idx += length + 1
                        length = int(msg[idx:idx+10], 16)
                        idx += 11
                        idData = msg[idx:idx+length]
                        idx += length + 1
                        idDataElements = idData.split(" ", 2)
                        message_obj.content.deviceIdUrn = idDataElements[0]
                        payload = None
                        if len(idDataElements) == 2:
                            payload = idDataElements[1]
                        if payload is None:
                            payload = msg[idx:-4]
                        message_obj.content.payload = payload
                        json_payload = json.loads(payload)
                        json_payload['payload'] = json.loads(
                            json_payload['payload'])
        self.msg_callback(message_obj)

    def on_error(self, ws, error):
        """Handle WebSocket Error."""
        _LOGGER.error("WebSocket Error {}".format(error))

    def on_close(self, ws):
        """Handle WebSocket Close."""
        _LOGGER.debug("WebSocket Connection Closed.")

    def on_open(self, ws):
        """Handle WebSocket Open."""
        ws.send("0x99d4f71a 0x0000001d A:HTUNE", OPCODE_BINARY)
        time.sleep(1)
        ws.send(self._encodeWSHandshake(), OPCODE_BINARY)
        time.sleep(1)
        ws.send(self._encodeGWHandshake(), OPCODE_BINARY)
        time.sleep(1)
        ws.send(self._encodeGWRegister(), OPCODE_BINARY)

    def _encodeWSHandshake(self):
        msg = "0xa6f6a951 "
        msg += "0x0000009c "
        msg += "{\"protocolName\":\"A:H\",\"parameters\":"
        msg += "{\"AlphaProtocolHandler.receiveWindowSize\":\"16\",\""
        msg += "AlphaProtocolHandler.maxFragmentSize\":\"16000\"}}TUNE"
        return msg

    def _encodeGWHandshake(self):
        msg = "MSG 0x00000361 "  # MSG channel
        msg += "0x360da09c f 0x00000001 "  # Message number with no cont
        msg += "0x019f0778 "  # Checksum
        msg += "0x0000009b "  # Content Length
        msg += "INI 0x00000003 1.0 0x00000024 "  # Message content
        msg += "01e09e62-f504-476c-85c8-9c97c8da26ed "  # Message UUID
        msg += "0x0000016978ff598c "  # Hex encoded timestamp
        msg += "END FABE"
        return msg

    def _encodeGWRegister(self):
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
    """Content Data Class."""

    def __init__(self):
        """Init for data."""
        self.messageType = ""
        self.protocolVersion = ""
        self.connectionUUID = ""
        self.established = 0
        self.timestampINI = 0
        self.timestampACK = 0
        self.subMessageType = ""
        self.channel = 0
        self.destIdUrn = ""
        self.deviceIdUrn = ""
        self.payload = ""
        self.payloadData = bytearray()


class Message:
    """Message Data Class."""

    def __init__(self):
        """Init for data."""
        self.service = ""
        self.content = Content()
        self.contentTune = ""
        self.messageType = ""
        self.channel = 0
        self.checksum = 0
        self.messageId = 0
        self.moreFlag = ""
        self.seq = 0
