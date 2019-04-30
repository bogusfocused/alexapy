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

    devices = []  # type: List[Dict[str, Union[Any, None, List]]]

    def __init__(self, device, login):
        """Initialize Alexa device."""
        self._device = device
        self._login = login
        self._session = login.session
        self._url = 'https://alexa.' + login.url

        csrf = self._session.cookies.get_dict()['csrf']
        self._session.headers['csrf'] = csrf

    @_catch_all_exceptions
    def _post_request(self, uri, data):
        return self._session.post(self._url + uri, json=data)

    @_catch_all_exceptions
    def _get_request(self, uri, data=None):
        return self._session.get(self._url + uri, json=data)

    def send_sequence(self, sequence, **kwargs):
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
        https://github.com/keatontaylor/custom_components/wiki#sequence-commands-versions--100
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
        self._post_request('/api/behaviors/preview',
                           data=data)

    def run_routine(self, utterance):
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
        automations = AlexaAPI.get_automations(self._login)
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
        self._post_request('/api/behaviors/preview',
                           data=data)

    def play_music(self, provider_id, search_phrase, customer_id=None):
        """Play Music based on search."""
        self.send_sequence("Alexa.Music.PlaySearchPhrase",
                           customerId=customer_id,
                           searchPhrase=search_phrase,
                           sanitizedSearchPhrase=search_phrase,
                           musicProviderId=provider_id)

    def send_tts(self, message, customer_id=None):
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
        self.send_sequence("Alexa.Speak",
                           customerId=customer_id,
                           textToSpeak=message)

    def send_announcement(self, message,
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
            for dev in AlexaAPI.devices:
                if dev['serialNumber'] in self._device._cluster_members:
                    devices.append({"deviceSerialNumber": dev['serialNumber'],
                                    "deviceTypeId": dev['deviceType']})
        elif targets and isinstance(targets, list):
            for dev in AlexaAPI.devices:
                if (dev['serialNumber'] in targets or
                        dev['accountName'] in targets):
                    devices.append({"deviceSerialNumber": dev['serialNumber'],
                                    "deviceTypeId": dev['deviceType']})
        else:
            devices.append({"deviceSerialNumber": self._device.unique_id,
                            "deviceTypeId": self._device._device_type})

        target = {"customerId": customer_id,
                  "devices": devices}
        self.send_sequence("AlexaAnnouncement",
                           customerId=customer_id,
                           expireAfter="PT5S",
                           content=content,
                           target=target)

    def send_mobilepush(self, message, title="AlexaAPI Message",
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
        self.send_sequence("Alexa.Notifications.SendMobilePush",
                           customerId=(customer_id if customer_id is not None
                                       else
                                       self._device._device_owner_customer_id),
                           notificationMessage=message,
                           alexaUrl="#v2/behaviors",
                           title=title)

    def set_media(self, data):
        """Select the media player."""
        self._post_request('/api/np/command?deviceSerialNumber=' +
                           self._device.unique_id + '&deviceType=' +
                           self._device._device_type, data=data)

    def previous(self):
        """Play previous."""
        self.set_media({"type": "PreviousCommand"})

    def next(self):
        """Play next."""
        self.set_media({"type": "NextCommand"})

    def pause(self):
        """Pause."""
        self.set_media({"type": "PauseCommand"})

    def play(self):
        """Play."""
        self.set_media({"type": "PlayCommand"})

    def set_volume(self, volume):
        """Set volume."""
        self.set_media({"type": "VolumeLevelCommand",
                        "volumeLevel": volume*100})
        self.send_sequence("Alexa.DeviceControls.Volume", value=volume*100)

    @_catch_all_exceptions
    def get_state(self):
        """Get playing state."""
        response = self._get_request('/api/np/player?deviceSerialNumber=' +
                                     self._device.unique_id +
                                     '&deviceType=' +
                                     self._device._device_type +
                                     '&screenWidth=2560')
        return response.json()

    @staticmethod
    @_catch_all_exceptions
    def get_bluetooth(login):
        """Get paired bluetooth devices."""
        session = login.session
        url = login.url
        response = session.get('https://alexa.' + url +
                               '/api/bluetooth?cached=false')
        return response.json()

    def set_bluetooth(self, mac):
        """Pair with bluetooth device with mac address."""
        self._post_request('/api/bluetooth/pair-sink/' +
                           self._device._device_type + '/' +
                           self._device.unique_id,
                           data={"bluetoothDeviceAddress": mac})

    def disconnect_bluetooth(self):
        """Disconnect all bluetooth devices."""
        self._post_request('/api/bluetooth/disconnect-sink/' +
                           self._device._device_type + '/' +
                           self._device.unique_id, data=None)

    @staticmethod
    @_catch_all_exceptions
    def get_devices(login):
        """Identify all Alexa devices."""
        session = login.session
        url = login.url
        response = session.get('https://alexa.' + url +
                               '/api/devices-v2/device')
        AlexaAPI.devices = response.json()['devices']
        return response.json()['devices']

    @staticmethod
    @_catch_all_exceptions
    def get_authentication(login):
        """Get authentication json."""
        session = login.session
        url = login.url
        response = session.get('https://alexa.' + url +
                               '/api/bootstrap')
        return response.json()['authentication']

    @staticmethod
    @_catch_all_exceptions
    def get_activities(login, items=10):
        """Get activities json."""
        session = login.session
        url = login.url
        response = session.get('https://alexa.' + url + '/api/activities?'
                               'startTime=&size=' + str(items) + '&offset=1')
        return response.json()['activities']

    @staticmethod
    @_catch_all_exceptions
    def get_device_preferences(login):
        """Identify all Alexa device professions."""
        session = login.session
        url = login.url
        response = session.get('https://alexa.' + url +
                               '/api/device-preferences')
        return response.json()

    @staticmethod
    @_catch_all_exceptions
    def get_automations(login, items=1000):
        """Identify all Alexa automations."""
        session = login.session
        url = login.url
        response = session.get('https://alexa.' + url +
                               '/api/behaviors/automations' + '?limit=' +
                               str(items))
        return response.json()

    @staticmethod
    def get_last_device_serial(login, items=10):
        """Identify the last device's serial number.

        This will store the [last items] activity records and find the latest
        entry where Echo successfully responded.
        """
        response = AlexaAPI.get_activities(login, items)
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
