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
from typing import (
    Any,
    Dict,
    List,  # noqa pylint: disable=unused-import
    Optional,
    Text,
)

from aiohttp import ClientResponse
from yarl import URL

import backoff

from .alexalogin import AlexaLogin
from .errors import (
    AlexapyLoginError,
    AlexapyTooManyRequestsError,
    AlexapyConnectionError,
)
from .helpers import _catch_all_exceptions, hide_email

_LOGGER = logging.getLogger(__name__)


class AlexaAPI:
    # pylint: disable=too-many-public-methods
    """Class for accessing a specific Alexa device using rest API.

    Args:
    device (AlexaClient): Instance of an AlexaClient to access
    login (AlexaLogin): Successfully logged in AlexaLogin

    """

    devices: Dict[Text, Any] = {}
    _sequence_queue: List[Dict[Any, Any]] = []
    _sequence_lock = asyncio.Lock()

    def __init__(self, device, login: AlexaLogin):
        """Initialize Alexa device."""
        self._device = device
        self._login = login
        self._session = login.session
        self._url: Text = "https://alexa." + login.url
        self._login._headers["Referer"] = "{}/spa/index.html".format(self._url)
        try:
            assert self._login._cookies is not None
            csrf = self._login._cookies["csrf"]
            self._login._headers["csrf"] = csrf
        except KeyError as ex:
            _LOGGER.warning(
                (
                    "AlexaLogin session is missing required token: %s "
                    "This may result in authorization errors, please report"
                ),
                ex,
            )

    @backoff.on_exception(
        backoff.expo,
        (AlexapyTooManyRequestsError, AlexapyConnectionError),
        max_time=60,
        max_tries=5,
        logger=__name__,
    )
    @_catch_all_exceptions
    async def _request(
        self,
        method: Text,
        uri: Text,
        data: Optional[Dict[Text, Text]] = None,
        query: Optional[Dict[Text, Text]] = None,
    ) -> ClientResponse:
        url: URL = URL(self._url + uri).update_query(query)
        # _LOGGER.debug("Trying %s: %s : with uri: %s data %s query %s",
        #               method,
        #               url,
        #               uri,
        #               data,
        #               query)
        response = await getattr(self._session, method)(
            url,
            json=data,
            cookies=self._login._cookies,
            headers=self._login._headers,
            ssl=self._login._ssl,
        )
        _LOGGER.debug(
            "%s: %s returned %s:%s:%s",
            response.request_info.method,
            response.request_info.url,
            response.status,
            response.reason,
            response.content_type,
        )
        if response.status == 401:
            raise AlexapyLoginError(response.reason)
        if response.status == 429:
            raise AlexapyTooManyRequestsError(response.reason)
        return response

    @_catch_all_exceptions
    async def _post_request(
        self, uri: Text, data: Optional[Dict[Text, Text]] = None
    ) -> ClientResponse:
        return await self._request("post", uri, data)

    @_catch_all_exceptions
    async def _put_request(
        self, uri: Text, data: Optional[Dict[Text, Text]] = None
    ) -> ClientResponse:
        return await self._request("put", uri, data)

    @_catch_all_exceptions
    async def _get_request(
        self, uri: Text, data: Optional[Dict[Text, Text]] = None
    ) -> ClientResponse:
        return await self._request("get", uri, data)

    @_catch_all_exceptions
    async def _del_request(
        self, uri: Text, data: Optional[Dict[Text, Text]] = None
    ) -> ClientResponse:
        return await self._request("delete", uri, data)

    @staticmethod
    @backoff.on_exception(
        backoff.expo,
        (AlexapyTooManyRequestsError, AlexapyConnectionError),
        max_time=60,
        max_tries=5,
        logger=__name__,
    )
    @_catch_all_exceptions
    async def _static_request(
        method: Text,
        login: AlexaLogin,
        uri: Text,
        data: Optional[Dict[Text, Text]] = None,
        query: Optional[Dict[Text, Text]] = None,
    ) -> ClientResponse:
        session = login.session
        url: URL = URL("https://alexa." + login.url + uri).update_query(query)
        # _LOGGER.debug("Trying static %s: %s : with uri: %s data %s query %s",
        #               method,
        #               url,
        #               uri,
        #               data,
        #               query)
        response = await getattr(session, method)(
            url,
            json=data,
            cookies=login._cookies,
            headers=login._headers,
            ssl=login._ssl,
        )
        _LOGGER.debug(
            "static %s: %s returned %s:%s:%s",
            response.request_info.method,
            response.request_info.url,
            response.status,
            response.reason,
            response.content_type,
        )
        if response.status == 401:
            raise AlexapyLoginError(response.reason)
        if response.status == 429:
            raise AlexapyTooManyRequestsError(response.reason)
        return response

    async def run_behavior(self, node_data, queue_delay: float = 1.5,) -> None:
        """Queue node_data for running a behavior in sequence.

        Amazon sequences and routines are based on node_data.

        Args:
            node_data (dict, list of dicts): The node_data to run.
            queue_delay (float, optional): The number of seconds to wait
                                          for commands to queue together.
                                          Defaults to 0.5.
                                          Must be positive.

        """
        sequence_json: Dict[Any, Any] = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": node_data,
        }
        if queue_delay > 0:
            sequence_json["startNode"] = {
                "@type": "com.amazon.alexa.behaviors.model.SerialNode",
                "nodesToExecute": [],
            }
            if AlexaAPI._sequence_queue:
                last_node = AlexaAPI._sequence_queue[-1]
                new_node = node_data
                if node_data and isinstance(node_data, list):
                    new_node = node_data[0]
                if (
                    last_node.get("operationPayload", {}).get("deviceSerialNumber")
                    and new_node.get("operationPayload", {}).get("deviceSerialNumber")
                ) and last_node.get("operationPayload", {}).get(
                    "deviceSerialNumber"
                ) != new_node.get(
                    "operationPayload", {}
                ).get(
                    "deviceSerialNumber"
                ):
                    _LOGGER.debug("Creating Parallel node")
                    sequence_json["startNode"][
                        "@type"
                    ] = "com.amazon.alexa.behaviors.model.ParallelNode"
            if isinstance(node_data, list):
                AlexaAPI._sequence_queue.extend(node_data)
            else:
                AlexaAPI._sequence_queue.append(node_data)
            items = len(AlexaAPI._sequence_queue)
            await asyncio.sleep(queue_delay)
            if items == len(AlexaAPI._sequence_queue):
                sequence_json["startNode"]["nodesToExecute"].extend(
                    AlexaAPI._sequence_queue
                )
                AlexaAPI._sequence_queue = []
                _LOGGER.debug("Creating sequence for %s items", items)
            else:
                _LOGGER.debug(
                    "Queue size changed while waiting %s seconds", queue_delay
                )
                return
        data = {
            "behaviorId": "PREVIEW",
            "sequenceJson": json.dumps(sequence_json),
            "status": "ENABLED",
        }
        _LOGGER.debug("Running behavior with data: %s", json.dumps(data))
        await self._post_request("/api/behaviors/preview", data=data)

    async def send_sequence(self, sequence: Text, **kwargs) -> None:
        """Send sequence command.

        This allows some programatic control of Echo device using the behaviors
        API and is the basis of play_music, send_announcement, and send_tts.

        Args:
        sequence (string): The Alexa sequence.  Supported list below.
        customerId (string): CustomerId to use for authorization. When none
                             specified this defaults to the device owner. Used
                             with households where others may have their own
                             music.
        **kwargs : Each named variable must match a recognized Amazon variable
                   within the operationPayload. Please see examples in
                   play_music, send_announcement, and send_tts.

        Supported sequences:
        Alexa.Weather.Play
        Alexa.Traffic.Play
        Alexa.FlashBriefing.Play
        Alexa.GoodMorning.Play
        Alexa.GoodNight.Play
        Alexa.SingASong.Play
        Alexa.TellStory.Play
        Alexa.FunFact.Play
        Alexa.Joke.Play
        Alexa.CleanUp.Play
        Alexa.Music.PlaySearchPhrase
        Alexa.Calendar.PlayTomorrow
        Alexa.Calendar.PlayToday
        Alexa.Calendar.PlayNext
        https://github.com/custom-components/alexa_media_player/wiki#sequence-commands-versions--100

        """
        operation_payload = {
            "deviceType": self._device._device_type,
            "deviceSerialNumber": self._device.unique_id,
            "locale": (self._device._locale if self._device._locale else "en-US"),
            "customerId": self._device._device_owner_customer_id,
        }
        if kwargs is not None:
            operation_payload.update(kwargs)
        node_data = {
            "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
            "type": sequence,
            "operationPayload": operation_payload,
        }
        await self.run_behavior(node_data)

    async def run_routine(self, utterance: Text) -> None:
        """Run Alexa automation routine.

        This allows running of defined Alexa automation routines.

        Args:
            utterance (string): The Alexa utterance to run the routine.

        """

        def _populate_device_info(node):
            """Search node and replace with this Alexa's device_info."""
            if "devices" in node:
                list(map(_populate_device_info, node["devices"]))
            elif "targetDevice" in node:
                _populate_device_info(node["targetDevice"])
            elif "operationPayload" in node:
                _populate_device_info(node["operationPayload"])
            else:
                if (
                    "deviceType" in node
                    and node["deviceType"] == "ALEXA_CURRENT_DEVICE_TYPE"
                ):
                    (node["deviceType"]) = self._device._device_type
                if (
                    "deviceSerialNumber" in node
                    and node["deviceSerialNumber"] == "ALEXA_CURRENT_DSN"
                ):
                    (node["deviceSerialNumber"]) = self._device.unique_id
                if "locale" in node and node["locale"] == "ALEXA_CURRENT_LOCALE":
                    (node["locale"]) = (
                        self._device._locale if self._device._locale else "en-US"
                    )

        automations = await AlexaAPI.get_automations(self._login)
        automation_id = None
        sequence = None
        for automation in automations:
            # skip other automations (e.g., time, GPS, buttons)
            if "utterance" not in automation["triggers"][0]["payload"]:
                continue
            a_utterance = automation["triggers"][0]["payload"]["utterance"]
            if a_utterance is not None and a_utterance.lower() == utterance.lower():
                automation_id = automation["automationId"]
                sequence = automation["sequence"]
        if automation_id is None or sequence is None:
            _LOGGER.debug("No routine found for %s", utterance)
            return
        new_nodes = []
        if "nodesToExecute" in sequence["startNode"]:
            # multiple sequences
            for node in sequence["startNode"]["nodesToExecute"]:
                if "nodesToExecute" in node:
                    # "@type":"com.amazon.alexa.behaviors.model.ParallelNode",
                    # nested nodesToExecute
                    for subnode in node["nodesToExecute"]:
                        _populate_device_info(subnode)
                else:
                    # "@type":"com.amazon.alexa.behaviors.model.SerialNode",
                    # nonNested nodesToExecute
                    _populate_device_info(node)
                new_nodes.append(node)
            sequence["startNode"]["nodesToExecute"] = new_nodes
            await self.run_behavior(sequence["startNode"]["nodesToExecute"])
        else:
            # Single entry with no nodesToExecute
            _populate_device_info(sequence["startNode"])
            await self.run_behavior(sequence["startNode"])

    async def play_music(
        self, provider_id: Text, search_phrase: Text, customer_id: Text = None
    ) -> None:
        """Play Music based on search."""
        await self.send_sequence(
            "Alexa.Music.PlaySearchPhrase",
            customerId=customer_id,
            searchPhrase=search_phrase,
            sanitizedSearchPhrase=search_phrase,
            musicProviderId=provider_id,
        )

    async def play_sound(self, sound_string_id: Text, customer_id: Text = None) -> None:
        """Play Alexa sound."""
        await self.send_sequence(
            "Alexa.Sound",
            customerId=customer_id,
            soundStringId=sound_string_id,
            skillId="amzn1.ask.1p.sound",
        )

    def process_targets(
        self, targets: Optional[List[Text]] = None
    ) -> List[Dict[Text, Text]]:
        """Process targets list to generate list of devices.

        Keyword Arguments
            targets {Optional[List[Text]]} -- List of serial numbers
                (default: {[]})

        Returns
            List[Dict[Text, Text] -- List of device dicts

        """
        targets = targets or []
        devices = []
        if self._device._device_family == "WHA":
            # Build group of devices based off _cluster_members
            for dev in AlexaAPI.devices[self._login.email]:
                if dev["serialNumber"] in self._device._cluster_members:
                    devices.append(
                        {
                            "deviceSerialNumber": dev["serialNumber"],
                            "deviceTypeId": dev["deviceType"],
                        }
                    )
        elif targets and isinstance(targets, list):
            for dev in AlexaAPI.devices[self._login.email]:
                if dev["serialNumber"] in targets or dev["accountName"] in targets:
                    devices.append(
                        {
                            "deviceSerialNumber": dev["serialNumber"],
                            "deviceTypeId": dev["deviceType"],
                        }
                    )
        else:
            devices.append(
                {
                    "deviceSerialNumber": self._device.unique_id,
                    "deviceTypeId": self._device._device_type,
                }
            )
        return devices

    async def send_tts(
        self,
        message: Text,
        customer_id: Text = None,
        targets: Optional[List[Text]] = None,
    ) -> None:
        """Send message for TTS at speaker.

        This is the old method which used Alexa Simon Says which did not work
        for WHA. This will not beep prior to sending. send_announcement
        should be used instead.

        Args:
        message (string): The message to speak
        customer_id (string): CustomerId to use for authorization. When none
                             specified this defaults to the device owner. Used
                             with households where others may have their own
                             music.
        targets (list(string)): WARNING: This is currently non functional due
                                to Alexa's API and is only included for future
                                proofing.
                                List of serialNumber or accountName to send the
                                tts to. Only those in this AlexaAPI
                                account will be searched. If None, announce
                                will be self.

        """
        target = {"customerId": customer_id, "devices": self.process_targets(targets)}
        await self.send_sequence(
            "Alexa.Speak",
            customerId=customer_id,
            textToSpeak=message,
            target=target,
            skillId="amzn1.ask.1p.saysomething",
        )

    async def send_announcement(
        self,
        message: Text,
        method: Text = "all",
        title: Text = "Announcement",
        customer_id: Text = None,
        targets: Optional[List[Text]] = None,
    ) -> None:
        # pylint: disable=too-many-arguments
        """Send announcment to Alexa devices.

        This uses the AlexaAnnouncement and allows visual display on the Show.
        It will beep prior to speaking.

        Args:
        message (string): The message to speak or display.
        method (string): speak, show, or all
        title (string): title to display on Echo show
        customer_id (string): CustomerId to use for authorization. When none
                             specified this defaults to the device owner. Used
                             with households where others may have their own
                             music.
        targets (list(string)): List of serialNumber or accountName to send the
                                announcement to. Only those in this AlexaAPI
                                account will be searched. If None, announce
                                will be self.

        """
        display = (
            {"title": "", "body": ""}
            if method.lower() == "speak"
            else {"title": title, "body": message}
        )
        speak = (
            {"type": "text", "value": ""}
            if method.lower() == "show"
            else {"type": "text", "value": message}
        )
        content = [
            {
                "locale": (self._device._locale if self._device._locale else "en-US"),
                "display": display,
                "speak": speak,
            }
        ]
        target = {"customerId": customer_id, "devices": self.process_targets(targets)}
        await self.send_sequence(
            "AlexaAnnouncement",
            customerId=customer_id,
            expireAfter="PT5S",
            content=content,
            target=target,
            skillId="amzn1.ask.1p.routines.messaging",
        )

    async def send_mobilepush(
        self, message: Text, title: Text = "AlexaAPI Message", customer_id: Text = None
    ) -> None:
        """Send announcment to Alexa devices.

        Push a message to mobile devices with the Alexa App. This probably
        should be a static method.

        Args:
        message (string): The message to push to the mobile device.
        title (string): Title for push notification
        customer_id (string): CustomerId to use for sending. When none
                              specified this defaults to the device owner.

        """
        await self.send_sequence(
            "Alexa.Notifications.SendMobilePush",
            customerId=(
                customer_id
                if customer_id is not None
                else self._device._device_owner_customer_id
            ),
            notificationMessage=message,
            alexaUrl="#v2/behaviors",
            title=title,
            skillId="amzn1.ask.1p.routines.messaging",
        )

    async def set_media(self, data: Dict[Text, Any]) -> None:
        """Select the media player."""
        await self._post_request(
            "/api/np/command?deviceSerialNumber="
            + self._device.unique_id
            + "&deviceType="
            + self._device._device_type,
            data=data,
        )

    async def previous(self) -> None:
        """Play previous."""
        await self.set_media({"type": "PreviousCommand"})

    async def next(self) -> None:
        """Play next."""
        await self.set_media({"type": "NextCommand"})

    async def pause(self) -> None:
        """Pause."""
        await self.set_media({"type": "PauseCommand"})

    async def play(self) -> None:
        """Play."""
        await self.set_media({"type": "PlayCommand"})

    async def forward(self) -> None:
        """Fastforward."""
        await self.set_media({"type": "ForwardCommand"})

    async def rewind(self) -> None:
        """Rewind."""
        await self.set_media({"type": "RewindCommand"})

    async def set_volume(self, volume: float) -> None:
        """Set volume."""
        await self.set_media(
            {"type": "VolumeLevelCommand", "volumeLevel": volume * 100}
        )
        await self.send_sequence("Alexa.DeviceControls.Volume", value=volume * 100)

    async def shuffle(self, setting: bool) -> None:
        """Shuffle.

        setting (string) : true or false
        """
        await self.set_media({"type": "ShuffleCommand", "shuffle": setting})

    async def repeat(self, setting: bool) -> None:
        """Repeat.

        setting (string) : true or false
        """
        await self.set_media({"type": "RepeatCommand", "repeat": setting})

    @_catch_all_exceptions
    async def get_state(self) -> Dict[Text, Any]:
        """Get playing state."""
        response = await self._get_request(
            "/api/np/player?deviceSerialNumber="
            + self._device.unique_id
            + "&deviceType="
            + self._device._device_type
            + "&screenWidth=2560"
        )
        return await response.json(content_type=None)

    @_catch_all_exceptions
    async def set_dnd_state(self, state: bool) -> None:
        """Set Do Not Disturb state.

        Args:
        state (boolean): true or false

        Returns json

        """
        data = {
            "deviceSerialNumber": self._device.unique_id,
            "deviceType": self._device._device_type,
            "enabled": state,
        }
        _LOGGER.debug("Setting DND state: %s data: %s", state, json.dumps(data))
        response = await self._put_request("/api/dnd/status", data=data)
        success = data == await response.json(content_type=None)
        _LOGGER.debug(
            "Success: %s Response: %s", success, await response.json(content_type=None)
        )
        return success

    @staticmethod
    @_catch_all_exceptions
    async def get_bluetooth(login) -> Dict[Text, Any]:
        """Get paired bluetooth devices."""
        response = await AlexaAPI._static_request(
            "get", login, "/api/bluetooth", query={"cached": "false"}
        )
        return await response.json(content_type=None)

    async def set_bluetooth(self, mac: Text) -> None:
        """Pair with bluetooth device with mac address."""
        await self._post_request(
            "/api/bluetooth/pair-sink/"
            + self._device._device_type
            + "/"
            + self._device.unique_id,
            data={"bluetoothDeviceAddress": mac},
        )

    async def disconnect_bluetooth(self) -> None:
        """Disconnect all bluetooth devices."""
        await self._post_request(
            "/api/bluetooth/disconnect-sink/"
            + self._device._device_type
            + "/"
            + self._device.unique_id,
            data=None,
        )

    @staticmethod
    @_catch_all_exceptions
    async def get_devices(login: AlexaLogin) -> Dict[Text, Any]:
        """Identify all Alexa devices."""
        response = await AlexaAPI._static_request(
            "get", login, "/api/devices-v2/device", query=None
        )
        AlexaAPI.devices[login.email] = (await response.json(content_type=None))[
            "devices"
        ]
        return AlexaAPI.devices[login.email]

    @staticmethod
    @_catch_all_exceptions
    async def get_authentication(login: AlexaLogin) -> Dict[Text, Any]:
        """Get authentication json."""
        response = await AlexaAPI._static_request(
            "get", login, "/api/bootstrap", query=None
        )
        return (await response.json(content_type=None))["authentication"]

    @staticmethod
    @_catch_all_exceptions
    async def get_activities(login: AlexaLogin, items: int = 10) -> Dict[Text, Any]:
        """Get activities json."""
        response = await AlexaAPI._static_request(
            "get",
            login,
            "/api/activities",
            query={"startTime": "", "size": items, "offset": 1},
        )
        return (await response.json(content_type=None))["activities"]

    @staticmethod
    @_catch_all_exceptions
    async def get_device_preferences(login: AlexaLogin) -> Dict[Text, Any]:
        """Identify all Alexa device preferences."""
        response = await AlexaAPI._static_request(
            "get", login, "/api/device-preferences", query={}
        )
        return await response.json(content_type=None)

    @staticmethod
    @_catch_all_exceptions
    async def get_automations(login: AlexaLogin, items: int = 1000) -> Dict[Text, Any]:
        """Identify all Alexa automations."""
        response = await AlexaAPI._static_request(
            "get", login, "/api/behaviors/automations", query={"limit": items}
        )
        return await response.json(content_type=None)

    @staticmethod
    async def get_last_device_serial(
        login: AlexaLogin, items: int = 10
    ) -> Optional[Dict[Text, Any]]:
        """Identify the last device's serial number.

        This will store the [last items] activity records and find the latest
        entry where Echo successfully responded.
        """
        response = await AlexaAPI.get_activities(login, items)
        if response is not None:
            for last_activity in response:
                # Ignore discarded activity records
                if (
                    last_activity["activityStatus"]
                    != "DISCARDED_NON_DEVICE_DIRECTED_INTENT"
                ):
                    return {
                        "serialNumber": (
                            last_activity["sourceDeviceIds"][0]["serialNumber"]
                        ),
                        "timestamp": last_activity["creationTimestamp"],
                    }
        return None

    @staticmethod
    @_catch_all_exceptions
    async def get_guard_state(login: AlexaLogin, entity_id: Text) -> Dict[Text, Any]:
        """Get state of Alexa guard.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin
        entity_id (string): applianceId of RedRock Panel

        Returns json

        """
        data = {"stateRequests": [{"entityId": entity_id, "entityType": "APPLIANCE"}]}
        response = await AlexaAPI._static_request(
            "post", login, "/api/phoenix/state", data=data
        )
        result = await response.json(content_type=None)
        _LOGGER.debug("get_guard_state response: %s", result)
        return result

    @staticmethod
    @_catch_all_exceptions
    async def set_guard_state(
        login: AlexaLogin, entity_id: Text, state: Text
    ) -> Dict[Text, Any]:
        """Set state of Alexa guard.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin
        entity_id (string): entityId of RedRock Panel
        state (string): ARMED_AWAY, ARMED_STAY

        Returns json

        """
        parameters = {"action": "controlSecurityPanel", "armState": state}
        data = {
            "controlRequests": [
                {
                    "entityId": entity_id,
                    "entityType": "APPLIANCE",
                    "parameters": parameters,
                }
            ]
        }
        response = await AlexaAPI._static_request(
            "put", login, "/api/phoenix/state", data=data
        )
        _LOGGER.debug(
            "set_guard_state response: %s for data: %s ",
            await response.json(content_type=None),
            json.dumps(data),
        )
        return await response.json(content_type=None)

    @staticmethod
    @_catch_all_exceptions
    async def get_guard_details(login: AlexaLogin) -> Dict[Text, Any]:
        """Get Alexa Guard details.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin

        Returns json

        """
        response = await AlexaAPI._static_request("get", login, "/api/phoenix")
        # _LOGGER.debug("Response: %s",
        #               await response.json(content_type=None))
        return json.loads((await response.json(content_type=None))["networkDetail"])

    @staticmethod
    @_catch_all_exceptions
    async def get_notifications(login: AlexaLogin) -> Dict[Text, Any]:
        """Get Alexa notifications.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin

        Returns json

        """
        response = await AlexaAPI._static_request("get", login, "/api/notifications")
        # _LOGGER.debug("Response: %s",
        #               response.json(content_type=None))
        return (await response.json(content_type=None))["notifications"]

    @staticmethod
    @_catch_all_exceptions
    async def set_notifications(login: AlexaLogin, data) -> Dict[Text, Any]:
        """Update Alexa notification.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin
        data : Data to pass to notifications

        Returns json

        """
        response = await AlexaAPI._static_request(
            "put", login, "/api/notifications", data=data
        )
        # _LOGGER.debug("Response: %s",
        #               response.json(content_type=None))
        return await response.json(content_type=None)

    @staticmethod
    @_catch_all_exceptions
    async def get_dnd_state(login: AlexaLogin) -> Dict[Text, Any]:
        """Get Alexa DND states.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin

        Returns json

        """
        response = await AlexaAPI._static_request(
            "get", login, "/api/dnd/device-status-list",
        )
        return await response.json(content_type=None)

    @staticmethod
    @_catch_all_exceptions
    async def clear_history(login: AlexaLogin, items: int = 50) -> bool:
        """Clear entries in history."""
        email = login.email
        response = await AlexaAPI._static_request(
            "get", login, "/api/activities", query={"size": items, "offset": -1}
        )
        import urllib.parse  # pylint: disable=import-outside-toplevel

        completed = True
        response_json = (await response.json(content_type=None))["activities"]
        if not response_json:
            _LOGGER.debug("%s:No history to delete.", hide_email(email))
            return True
        _LOGGER.debug(
            "%s:Attempting to delete %s items from history",
            hide_email(email),
            len(response_json),
        )
        for activity in response_json:
            response = await AlexaAPI._static_request(
                "delete",
                login,
                "/api/activities/{}".format(urllib.parse.quote_plus(activity["id"])),
            )
            if response.status == 404:
                _LOGGER.warning(
                    (
                        "%s:Unable to delete %s: %s: \n"
                        "There is no voice recording to delete. "
                        "Please manually delete the entry in the Alexa app."
                    ),
                    hide_email(email),
                    activity["id"],
                    response.reason,
                )
                completed = False
            elif response.status == 200:
                _LOGGER.debug(
                    "%s:Succesfully deleted %s", hide_email(email), activity["id"],
                )
        return completed
