"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
VERSION 1.0.0
"""
import logging
import json


_LOGGER = logging.getLogger(__name__)


class AlexaAPI():
    """Class for accessing a specific Alexa device using rest API.

    Args:
    device (AlexaClient): Instance of an AlexaClient to access
    login (AlexaLogin): Successfully logged in AlexaLogin
    """

    def __init__(self, device, login):
        """Initialize Alexa device."""
        self._device = device
        self._login = login
        self._session = login._session
        self._url = 'https://alexa.' + login._url

        csrf = self._session.cookies.get_dict()['csrf']
        self._session.headers['csrf'] = csrf

    def _catchAllExceptions(func):
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as ex:
                template = ("An exception of type {0} occurred."
                            " Arguments:\n{1!r}")
                message = template.format(type(ex).__name__, ex.args)
                _LOGGER.error(("An error occured accessing AlexaAPI: "
                               "{}").format(message))
                return None
        return wrapper

    @_catchAllExceptions
    def _post_request(self, uri, data):
        return self._session.post(self._url + uri, json=data)

    @_catchAllExceptions
    def _get_request(self, uri, data=None):
        return self._session.get(self._url + uri, json=data)

    def send_sequence(self, sequence, **kwargs):
        """Send sequence command.

        This allows some programatic control of Echo device using the behaviors
        API and is the basis of play_music and send_tts.

        Args:
        sequence (string): The Alexa sequence.  Supported list below.
        customerId (string): CustomerId to use for authorization. When none
                             specified this defaults to the device owner. Used
                             with households where others may have their own
                             music.
        **kwargs : Each named variable must match a recognized Amazon variable
                   within the operationPayload. Please see examples in
                   play_music and send_tts.

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
        Alexa.Music.PlaySearchPhrase
        Alexa.Calendar.PlayTomorrow
        Alexa.Calendar.PlayToday
        Alexa.Calendar.PlayNext
        """
        operationPayload = {
                "deviceType": self._device._device_type,
                "deviceSerialNumber": self._device.unique_id,
                "locale": "en-US",
                "customerId": self._device._device_owner_customer_id
               }
        if kwargs is not None:
            operationPayload.update(kwargs)
        sequenceJson = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": {
                 "@type":
                 "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
                 "type": sequence,
                 "operationPayload": operationPayload
                }
        }
        data = {
            "behaviorId": "PREVIEW",
            "sequenceJson": json.dumps(sequenceJson),
            "status": "ENABLED"
        }
        _LOGGER.debug("Running sequence: %s data: %s" % (sequence,
                                                         json.dumps(data)))
        self._post_request('/api/behaviors/preview',
                           data=data)

    def run_routine(self, utterance):
        """Run Alexa automation routine.

        This allows running of defined Alexa automation routines.

        Args:
        utterance (string): The Alexa utterance to run the routine.
        """
        automations = AlexaAPI.get_automations(self._login)
        automationId = None
        sequence = None
        for automation in automations:
            a_utterance = automation['triggers'][0]['payload']['utterance']
            if (a_utterance is not None and
                    a_utterance.lower() == utterance.lower()):
                automationId = automation['automationId']
                sequence = automation['sequence']
        if (automationId is None or sequence is None):
            _LOGGER.debug("No routine found for %s" % (utterance))
            return
        newNodes = []
        for node in sequence['startNode']['nodesToExecute']:
            node['operationPayload']['deviceType'] = self._device._device_type
            (node['operationPayload']
                 ['deviceSerialNumber']) = self._device.unique_id
            newNodes.append(node)
        sequence['startNode']['nodesToExecute'] = newNodes

        data = {
            "behaviorId": automationId,
            "sequenceJson": json.dumps(sequence),
            "status": "ENABLED"
        }
        _LOGGER.debug("Running routine: %s with data: %s" % (utterance,
                                                             json.dumps(data)))
        self._post_request('/api/behaviors/preview',
                           data=data)

    def play_music(self, provider_id, search_phrase, customerId=None):
        """Play Music based on search."""
        self.send_sequence("Alexa.Music.PlaySearchPhrase",
                           customerId=customerId,
                           searchPhrase=search_phrase,
                           sanitizedSearchPhrase=search_phrase,
                           musicProviderId=provider_id)

    def send_tts(self, message, customerId=None):
        """Send message for TTS at speaker."""
        self.send_sequence("Alexa.Speak",
                           customerId=customerId,
                           textToSpeak=message)

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

    @_catchAllExceptions
    def get_state(self):
        """Get playing state."""
        response = self._get_request('/api/np/player?deviceSerialNumber=' +
                                     self._device.unique_id +
                                     '&deviceType=' +
                                     self._device._device_type +
                                     '&screenWidth=2560')
        return response.json()

    @staticmethod
    @_catchAllExceptions
    def get_bluetooth(login):
        """Get paired bluetooth devices."""
        session = login._session
        url = login._url
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
    @_catchAllExceptions
    def get_devices(login):
        """Identify all Alexa devices."""
        session = login._session
        url = login._url
        response = session.get('https://alexa.' + url +
                               '/api/devices-v2/device')
        return response.json()['devices']

    @staticmethod
    @_catchAllExceptions
    def get_authentication(login):
        """Get authentication json."""
        session = login._session
        url = login._url
        response = session.get('https://alexa.' + url +
                               '/api/bootstrap')
        return response.json()['authentication']

    @staticmethod
    @_catchAllExceptions
    def get_activities(login, items=10):
        """Get activities json."""
        session = login._session
        url = login._url
        response = session.get('https://alexa.' + url + '/api/activities?'
                               'startTime=&size=' + str(items) + '&offset=1')
        return response.json()['activities']

    @staticmethod
    @_catchAllExceptions
    def get_automations(login):
        """Identify all Alexa automations."""
        session = login._session
        url = login._url
        response = session.get('https://alexa.' + url +
                               '/api/behaviors/automations')
        return response.json()

    @staticmethod
    def get_last_device_serial(login, items=10):
        """Identify the last device's serial number.

        This will pull the last items activity records and find the latest
        entry where Echo successfully responded.
        """
        response = AlexaAPI.get_activities(login, items)
        if (response is not None):
            for last_activity in response:
                # Ignore discarded activity records
                if (last_activity['activityStatus']
                        != 'DISCARDED_NON_DEVICE_DIRECTED_INTENT'):
                    return {
                            'serialNumber': (last_activity['sourceDeviceIds']
                                                          [0]
                                                          ['serialNumber']),
                            'timestamp': last_activity['creationTimestamp']
                            }
        return None
