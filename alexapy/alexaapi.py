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
from typing import Any, Dict, List, Union  # noqa pylint: disable=unused-import

_LOGGER = logging.getLogger(__name__)


def _catch_all_exceptions(func):
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as ex:  # pylint: disable=broad-except
            template = ("An exception of type {0} occurred."
                        " Arguments:\n{1!r}")
            message = template.format(type(ex).__name__, ex.args)
            _LOGGER.error("An error occured accessing AlexaAPI: %s", (message))
            return None
    return wrapper


class AlexaAPI():
    # pylint: disable=too-many-public-methods
    """Class for accessing a specific Alexa device using rest API.

    Args:
    device (AlexaClient): Instance of an AlexaClient to access
    login (AlexaLogin): Successfully logged in AlexaLogin

    """

    devices = {}  # type: Dict[str, List[Dict[str, Union[Any, None, List]]]]

    def __init__(self, device, login):
        """Initialize Alexa device."""
        self._device = device
        self._login = login
        self._session = login.session
        self._url = 'https://alexa.' + login.url
        try:
            csrf = self._login._cookies['csrf']
            self._login._headers['csrf'] = csrf
        except KeyError as ex:
            _LOGGER.error(("AlexaLogin session is missing required token: %s "
                           "this is an unrecoverable error, please report"),
                          ex)
            login.reset_login()

    @_catch_all_exceptions
    async def _post_request(self, uri, data):
        return await self._session.post(self._url + uri, json=data,
                                        cookies=self._login._cookies,
                                        headers=self._login._headers)

    @_catch_all_exceptions
    async def _put_request(self, uri, data):
        return await self._session.put(self._url + uri, json=data,
                                       cookies=self._login._cookies,
                                       headers=self._login._headers)

    @_catch_all_exceptions
    async def _get_request(self, uri, data=None):
        return await self._session.get(self._url + uri, json=data,
                                       cookies=self._login._cookies,
                                       headers=self._login._headers)

    async def send_sequence(self, sequence, **kwargs):
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
            "locale": (self._device._locale if self._device._locale
                       else "en-US"),
            "customerId": self._device._device_owner_customer_id
            }
        if kwargs is not None:
            operation_payload.update(kwargs)
        sequence_json = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": {
                "@type":
                "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
                "type": sequence,
                "operationPayload": operation_payload
                }
        }
        data = {
            "behaviorId": "PREVIEW",
            "sequenceJson": json.dumps(sequence_json),
            "status": "ENABLED"
        }
        _LOGGER.debug("Running sequence: %s data: %s",
                      sequence,
                      json.dumps(data))
        await self._post_request('/api/behaviors/preview',
                                 data=data)

    async def run_routine(self, utterance):
        """Run Alexa automation routine.

        This allows running of defined Alexa automation routines.

        Args:
        utterance (string): The Alexa utterance to run the routine.

        """
        def _populate_device_info(node):
            """Search node and replace with this Alexa's device_info."""
            if 'devices' in node:
                list(map(_populate_device_info, node['devices']))
            elif 'operationPayload' in node:
                _populate_device_info(node['operationPayload'])
            else:
                if ('deviceType' in node and
                        node['deviceType'] == 'ALEXA_CURRENT_DEVICE_TYPE'):
                    (node['deviceType']) = self._device._device_type
                if ('deviceSerialNumber' in node and
                        node['deviceSerialNumber'] == 'ALEXA_CURRENT_DSN'):
                    (node['deviceSerialNumber']) = self._device.unique_id
                if ('locale' in node and
                        node['locale'] == 'ALEXA_CURRENT_LOCALE'):
                    (node['locale']) = (self._device._locale if
                                        self._device._locale
                                        else "en-US")
        automations = await AlexaAPI.get_automations(self._login)
        automation_id = None
        sequence = None
        for automation in automations:
            # skip other automations (e.g., time, GPS, buttons)
            if 'utterance' not in automation['triggers'][0]['payload']:
                continue
            a_utterance = automation['triggers'][0]['payload']['utterance']
            if (a_utterance is not None and
                    a_utterance.lower() == utterance.lower()):
                automation_id = automation['automationId']
                sequence = automation['sequence']
        if (automation_id is None or sequence is None):
            _LOGGER.debug("No routine found for %s", utterance)
            return
        new_nodes = []
        if 'nodesToExecute' in sequence['startNode']:
            # multiple sequences
            for node in sequence['startNode']['nodesToExecute']:
                if 'nodesToExecute' in node:
                    # "@type":"com.amazon.alexa.behaviors.model.ParallelNode",
                    # nested nodesToExecute
                    for subnode in node['nodesToExecute']:
                        _populate_device_info(subnode)
                else:
                    # "@type":"com.amazon.alexa.behaviors.model.SerialNode",
                    # nonNested nodesToExecute
                    _populate_device_info(node)
                new_nodes.append(node)
            sequence['startNode']['nodesToExecute'] = new_nodes
        else:
            # Single entry with no nodesToExecute
            _populate_device_info(sequence['startNode'])
        data = {
            "behaviorId": automation_id,
            "sequenceJson": json.dumps(sequence),
            "status": "ENABLED"
        }
        _LOGGER.debug("Running routine: %s with data: %s",
                      utterance,
                      json.dumps(data))
        await self._post_request('/api/behaviors/preview',
                                 data=data)

    async def play_music(self, provider_id, search_phrase, customer_id=None):
        """Play Music based on search."""
        await self.send_sequence("Alexa.Music.PlaySearchPhrase",
                                 customerId=customer_id,
                                 searchPhrase=search_phrase,
                                 sanitizedSearchPhrase=search_phrase,
                                 musicProviderId=provider_id)

    async def send_tts(self, message, customer_id=None):
        """Send message for TTS at speaker.

        This is the old method which used Alexa Simon Says which did not work
        for WHA. This will not beep prior to sending. send_announcement
        should be used instead.

        Args:
        message (string): The message to speak
        customerId (string): CustomerId to use for authorization. When none
                             specified this defaults to the device owner. Used
                             with households where others may have their own
                             music.

        """
        await self.send_sequence("Alexa.Speak",
                                 customerId=customer_id,
                                 textToSpeak=message)

    async def send_announcement(self, message,
                                method="all",
                                title="Announcement",
                                customer_id=None,
                                targets=None):
        # pylint: disable=too-many-arguments
        """Send announcment to Alexa devices.

        This uses the AlexaAnnouncement and allows visual display on the Show.
        It will beep prior to speaking.

        Args:
        message (string): The message to speak or display.
        method (string): speak, show, or all
        title (string): title to display on Echo show
        customerId (string): CustomerId to use for authorization. When none
                             specified this defaults to the device owner. Used
                             with households where others may have their own
                             music.
        targets (list(string)): List of serialNumber or accountName to send the
                                announcement to. Only those in this AlexaAPI
                                account will be searched. If None, announce
                                will be self.

        """
        display = ({"title": "", "body": ""} if method.lower() == "speak" else
                   {"title": title, "body": message})
        speak = ({"type": "text", "value": ""} if method.lower() == "show" else
                 {"type": "text", "value": message})
        content = [{"locale": (self._device._locale if self._device._locale
                               else "en-US"),
                    "display": display,
                    "speak": speak}]
        devices = []
        if self._device._device_family == "WHA":
            # Build group of devices based off _cluster_members
            for dev in AlexaAPI.devices[self._login.email]:
                if dev['serialNumber'] in self._device._cluster_members:
                    devices.append({"deviceSerialNumber": dev['serialNumber'],
                                    "deviceTypeId": dev['deviceType']})
        elif targets and isinstance(targets, list):
            for dev in AlexaAPI.devices[self._login.email]:
                if (dev['serialNumber'] in targets or
                        dev['accountName'] in targets):
                    devices.append({"deviceSerialNumber": dev['serialNumber'],
                                    "deviceTypeId": dev['deviceType']})
        else:
            devices.append({"deviceSerialNumber": self._device.unique_id,
                            "deviceTypeId": self._device._device_type})

        target = {"customerId": customer_id,
                  "devices": devices}
        await self.send_sequence("AlexaAnnouncement",
                                 customerId=customer_id,
                                 expireAfter="PT5S",
                                 content=content,
                                 target=target)

    async def send_mobilepush(self, message, title="AlexaAPI Message",
                              customer_id=None):
        """Send announcment to Alexa devices.

        Push a message to mobile devices with the Alexa App. This probably
        should be a static method.

        Args:
        message (string): The message to push to the mobile device.
        title (string): Title for push notification
        customer_id (string): CustomerId to use for sending. When none
                              specified this defaults to the device owner.

        """
        await self.send_sequence("Alexa.Notifications.SendMobilePush",
                                 customerId=(
                                     customer_id if customer_id is not None
                                     else
                                     self._device._device_owner_customer_id),
                                 notificationMessage=message,
                                 alexaUrl="#v2/behaviors",
                                 title=title)

    async def set_media(self, data):
        """Select the media player."""
        await self._post_request('/api/np/command?deviceSerialNumber=' +
                                 self._device.unique_id + '&deviceType=' +
                                 self._device._device_type, data=data)

    async def previous(self):
        """Play previous."""
        await self.set_media({"type": "PreviousCommand"})

    async def next(self):
        """Play next."""
        await self.set_media({"type": "NextCommand"})

    async def pause(self):
        """Pause."""
        await self.set_media({"type": "PauseCommand"})

    async def play(self):
        """Play."""
        await self.set_media({"type": "PlayCommand"})

    async def forward(self):
        """Fastforward."""
        await self.set_media({"type": "ForwardCommand"})

    async def rewind(self):
        """Rewind."""
        await self.set_media({"type": "RewindCommand"})

    async def set_volume(self, volume):
        """Set volume."""
        await self.set_media({"type": "VolumeLevelCommand",
                              "volumeLevel": volume*100})
        await self.send_sequence("Alexa.DeviceControls.Volume",
                                 value=volume*100)

    async def shuffle(self, setting):
        """Shuffle.

        setting (string) : true or false
        """
        await self.set_media({"type": "ShuffleCommand",
                              "shuffle": setting})

    async def repeat(self, setting):
        """Repeat.

        setting (string) : true or false
        """
        await self.set_media({"type": "RepeatCommand",
                              "repeat": setting})

    @_catch_all_exceptions
    async def get_state(self):
        """Get playing state."""
        response = await self._get_request('/api/np/player?deviceSerialNumber='
                                           +
                                           self._device.unique_id +
                                           '&deviceType=' +
                                           self._device._device_type +
                                           '&screenWidth=2560')
        return await response.json()

    @_catch_all_exceptions
    async def set_dnd_state(self, state):
        """Set Do Not Disturb state.

        Args:
        state (boolean): true or false

        Returns json

        """
        data = {
            "deviceSerialNumber": self._device.unique_id,
            "deviceType": self._device._device_type,
            "enabled": state
        }
        _LOGGER.debug("Setting DND state: %s data: %s",
                      state,
                      json.dumps(data))
        response = await self._put_request('/api/dnd/status',
                                           data=data)
        success = data == await response.json()
        _LOGGER.debug("Success: %s Response: %s",
                      success, await response.json())
        return success

    @staticmethod
    @_catch_all_exceptions
    async def get_bluetooth(login):
        """Get paired bluetooth devices."""
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/bluetooth?cached=false',
                                     cookies=login._cookies,
                                     headers=login._headers)
        return await response.json()

    async def set_bluetooth(self, mac):
        """Pair with bluetooth device with mac address."""
        await self._post_request('/api/bluetooth/pair-sink/' +
                                 self._device._device_type + '/' +
                                 self._device.unique_id,
                                 data={"bluetoothDeviceAddress": mac})

    async def disconnect_bluetooth(self):
        """Disconnect all bluetooth devices."""
        await self._post_request('/api/bluetooth/disconnect-sink/' +
                                 self._device._device_type + '/' +
                                 self._device.unique_id,
                                 data=None)

    @staticmethod
    @_catch_all_exceptions
    async def get_devices(login):
        """Identify all Alexa devices."""
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/devices-v2/device',
                                     cookies=login._cookies,
                                     headers=login._headers)
        AlexaAPI.devices[login.email] = (await response.json())['devices']
        return (await response.json())['devices']

    @staticmethod
    @_catch_all_exceptions
    async def get_authentication(login):
        """Get authentication json."""
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/bootstrap',
                                     cookies=login._cookies,
                                     headers=login._headers)
        return (await response.json())['authentication']

    @staticmethod
    @_catch_all_exceptions
    async def get_activities(login, items=10):
        """Get activities json."""
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/activities?'
                                     'startTime=&size=' + str(items) +
                                     '&offset=1',
                                     cookies=login._cookies,
                                     headers=login._headers)
        return (await response.json())['activities']

    @staticmethod
    @_catch_all_exceptions
    async def get_device_preferences(login):
        """Identify all Alexa device preferences."""
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/device-preferences',
                                     cookies=login._cookies,
                                     headers=login._headers)
        return await response.json()

    @staticmethod
    @_catch_all_exceptions
    async def get_automations(login, items=1000):
        """Identify all Alexa automations."""
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/behaviors/automations' + '?limit=' +
                                     str(items),
                                     cookies=login._cookies,
                                     headers=login._headers)
        return await response.json()

    @staticmethod
    async def get_last_device_serial(login, items=10):
        """Identify the last device's serial number.

        This will store the [last items] activity records and find the latest
        entry where Echo successfully responded.
        """
        response = await AlexaAPI.get_activities(login, items)
        if response is not None:
            for last_activity in response:
                # Ignore discarded activity records
                if (last_activity['activityStatus']
                        != 'DISCARDED_NON_DEVICE_DIRECTED_INTENT'):
                    return {
                        'serialNumber': (last_activity['sourceDeviceIds'][0]
                                         ['serialNumber']),
                        'timestamp': last_activity['creationTimestamp']}
        return None

    @staticmethod
    @_catch_all_exceptions
    async def get_guard_state(login, entity_id):
        """Get state of Alexa guard.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin
        entity_id (string): applianceId of RedRock Panel

        Returns json

        """
        session = login.session
        url = login.url
        data = {"stateRequests": [{"entityId": entity_id,
                                   "entityType": "APPLIANCE"}]}
        response = await session.post('https://alexa.' + url +
                                      '/api/phoenix/state',
                                      cookies=login._cookies,
                                      headers=login._headers,
                                      json=data)
        _LOGGER.debug("get_guard_state response: %s",
                      await response.json())
        return await response.json()

    @staticmethod
    @_catch_all_exceptions
    async def set_guard_state(login, entity_id, state):
        """Set state of Alexa guard.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin
        entity_id (string): entityId of RedRock Panel
        state (string): ARMED_AWAY, ARMED_STAY

        Returns json

        """
        session = login.session
        url = login.url
        parameters = {"action": "controlSecurityPanel",
                      "armState": state}
        data = {"controlRequests": [{"entityId": entity_id,
                                     "entityType": "APPLIANCE",
                                     "parameters": parameters}]}
        response = await session.put('https://alexa.' + url +
                                     '/api/phoenix/state',
                                     cookies=login._cookies,
                                     headers=login._headers,
                                     json=data)
        _LOGGER.debug("set_guard_state response: %s for data: %s ",
                      await response.json(), json.dumps(data))
        return await response.json()

    @staticmethod
    @_catch_all_exceptions
    async def get_guard_details(login):
        """Get Alexa Guard details.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin

        Returns json

        """
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/phoenix',
                                     cookies=login._cookies,
                                     headers=login._headers)
        # _LOGGER.debug("Response: %s",
        #               await response.json())
        return json.loads((await response.json())['networkDetail'])

    @staticmethod
    @_catch_all_exceptions
    async def get_notifications(login):
        """Get Alexa notifications.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin

        Returns json

        """
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/notifications',
                                     cookies=login._cookies,
                                     headers=login._headers)
        # _LOGGER.debug("Response: %s",
        #               response.json())
        return await response.json()['notifications']

    @staticmethod
    @_catch_all_exceptions
    async def get_dnd_state(login):
        """Get Alexa DND states.

        Args:
        login (AlexaLogin): Successfully logged in AlexaLogin

        Returns json

        """
        session = login.session
        url = login.url
        response = await session.get('https://alexa.' + url +
                                     '/api/dnd/device-status-list',
                                     cookies=login._cookies,
                                     headers=login._headers)
        # _LOGGER.debug("Response: %s",
        #               response.json())
        return await response.json()
