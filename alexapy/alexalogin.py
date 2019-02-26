#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""

import logging

import requests

_LOGGER = logging.getLogger(__name__)


class AlexaLogin():
    # pylint: disable=too-many-instance-attributes
    """Class to handle login connection to Alexa. This class will not reconnect.

    Args:
    url (string): Localized Amazon domain (e.g., amazon.com)
    email (string): Amazon login account
    password (string): Password for Amazon login account
    outputpath (string): Local path with write access for storing files
    debug (boolean): Enable additional debugging including debug file creation
    """

    def __init__(self, url, email, password, outputpath, debug=False):
        # pylint: disable=too-many-arguments
        """Set up initial connection and log in."""
        prefix = "alexa_media"
        self._url = url
        self._email = email
        self._password = password
        self._session = None
        self._data = None
        self.status = {}
        self._cookiefile = outputpath("{}.{}.pickle".format(prefix, email))
        self._debugpost = outputpath("{}{}post.html".format(prefix, email))
        self._debugget = outputpath("{}{}get.html".format(prefix, email))
        self._lastreq = None
        self._debug = debug

        self.login_with_cookie()

    @property
    def email(self):
        """Return email for this Login."""
        return self._email

    @property
    def session(self):
        """Return session for this Login."""
        return self._session

    @property
    def url(self):
        """Return session for this Login."""
        return self._url

    def login_with_cookie(self):
        """Attempt to login after loading cookie."""
        import pickle
        cookies = None

        if self._cookiefile:
            try:
                _LOGGER.debug(
                    "Trying cookie from file %s", self._cookiefile)
                with open(self._cookiefile, 'rb') as myfile:
                    cookies = pickle.load(myfile)
                    _LOGGER.debug("cookie loaded: %s", cookies)
            except OSError as ex:
                template = ("An exception of type {0} occurred."
                            " Arguments:\n{1!r}")
                message = template.format(type(ex).__name__, ex.args)
                _LOGGER.debug(
                    "Error loading pickled cookie from %s: %s",
                    self._cookiefile, message)

        self.login(cookies=cookies)

    def reset_login(self):
        """Remove data related to existing login."""
        self._session = None
        self._data = None
        self._lastreq = None
        self.status = {}
        import os
        if ((self._cookiefile) and os.path.exists(self._cookiefile)):
            try:
                _LOGGER.debug(
                    "Trying to delete cookie file %s", self._cookiefile)
                os.remove(self._cookiefile)
            except OSError as ex:
                template = ("An exception of type {0} occurred."
                            " Arguments:\n{1!r}")
                message = template.format(type(ex).__name__, ex.args)
                _LOGGER.debug(
                    "Error deleting cookie %s: %s", self._cookiefile, message)

    @classmethod
    def get_inputs(cls, soup, searchfield=None):
        """Parse soup for form with searchfield."""
        searchfield = searchfield or {'name': 'signIn'}
        data = {}
        form = soup.find('form', searchfield)
        for field in form.find_all('input'):
            try:
                data[field['name']] = ""
                data[field['name']] = field['value']
            except BaseException:  # pylint: disable=bare-except
                pass
        return data

    def test_loggedin(self, cookies=None):
        """Function that will test the connection is logged in.

        Attempts to get authenticaton and compares to expected login email
        Returns false if unsuccesful getting json or the emails don't match
        """
        if self._session is None:
            #  initiate session

            self._session = requests.Session()

            #  define session headers
            self._session.headers = {
                'User-Agent': ('Mozilla/5.0 (Windows NT 6.3; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/68.0.3440.106 Safari/537.36'),
                'Accept': ('text/html,application/xhtml+xml, '
                           'application/xml;q=0.9,*/*;q=0.8'),
                'Accept-Language': '*'
            }
            self._session.cookies = cookies

        get_resp = self._session.get('https://alexa.' + self._url +
                                     '/api/bootstrap')
        # with open(self._debugget, mode='wb') as localfile:
        #     localfile.write(get_resp.content)

        try:
            from json.decoder import JSONDecodeError
            from simplejson import JSONDecodeError as SimpleJSONDecodeError
            # Need to catch both as Python 3.5 appears to use simplejson
        except ImportError:
            JSONDecodeError = ValueError
        try:
            email = get_resp.json()['authentication']['customerEmail']
        except (JSONDecodeError, SimpleJSONDecodeError) as ex:
            # ValueError is necessary for Python 3.5 for some reason
            template = ("An exception of type {0} occurred."
                        " Arguments:\n{1!r}")
            message = template.format(type(ex).__name__, ex.args)
            _LOGGER.debug("Not logged in: %s", message)
            return False
        if email.lower() == self._email.lower():
            _LOGGER.debug("Logged in as %s", email)
            return True
        _LOGGER.debug("Not logged in due to email mismatch")
        self.reset_login()
        return False

    def login(self, cookies=None, captcha=None, securitycode=None,
              claimsoption=None, verificationcode=None):
        # pylint: disable=too-many-branches,too-many-arguments,too-many-locals,
        # pylint: disable=too-many-statements
        """Login to Amazon."""
        from bs4 import BeautifulSoup
        import pickle

        if (cookies is not None and self.test_loggedin(cookies)):
            _LOGGER.debug("Using cookies to log in")
            self.status = {}
            self.status['login_successful'] = True
            _LOGGER.debug("Log in successful with cookies")
            return
        _LOGGER.debug("No valid cookies for log in; using credentials")
        #  site = 'https://www.' + self._url + '/gp/sign-in.html'
        #  use alexa site instead
        site = 'https://alexa.' + self._url + '/api/devices-v2/device'
        if self._session is None:
            #  initiate session

            self._session = requests.Session()

            #  define session headers
            self._session.headers = {
                'User-Agent': ('Mozilla/5.0 (Windows NT 6.3; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/68.0.3440.106 Safari/537.36'),
                'Accept': ('text/html,application/xhtml+xml, '
                           'application/xml;q=0.9,*/*;q=0.8'),
                'Accept-Language': '*'
            }

        if self._lastreq is not None:
            site = self._lastreq.url
            _LOGGER.debug("Loaded last request to %s ", site)
            html = self._lastreq.text
            #  get BeautifulSoup object of the html of the login page
            if self._debug:
                with open(self._debugget, mode='wb') as localfile:
                    localfile.write(self._lastreq.content)

            soup = BeautifulSoup(html, 'html.parser')
            site = soup.find('form').get('action')
            if site is None:
                site = self._lastreq.url
            elif site == 'verify':
                import re
                site = re.search(r'(.+)/(.*)',
                                 self._lastreq.url).groups()[0] + "/verify"

        if self._data is None:
            resp = self._session.get(site)
            self._lastreq = resp
            if resp.history:
                _LOGGER.debug("Get to %s was redirected to %s",
                              site,
                              resp.url)
                self._session.headers['Referer'] = resp.url
            else:
                _LOGGER.debug("Get to %s was not redirected", site)
                self._session.headers['Referer'] = site

            html = resp.text
            #  get BeautifulSoup object of the html of the login page
            if self._debug:
                with open(self._debugget, mode='wb') as localfile:
                    localfile.write(resp.content)

            soup = BeautifulSoup(html, 'html.parser')
            #  scrape login page to get all the inputs required for login
            self._data = self.get_inputs(soup)
            site = soup.find('form', {'name': 'signIn'}).get('action')

        # _LOGGER.debug("Init Form Data: {}".format(self._data))

        #  add username and password to the data for post request
        #  check if there is an input field
        if "email" in self._data:
            self._data['email'] = self._email.encode('utf-8')
        if "password" in self._data:
            self._data['password'] = self._password.encode('utf-8')
        if "rememberMe" in self._data:
            self._data['rememberMe'] = "true".encode('utf-8')

        status = {}
        _LOGGER.debug(("Preparing post to %s Captcha: %s"
                       " SecurityCode: %s Claimsoption: %s "
                       "VerificationCode: %s"),
                      site,
                      captcha,
                      securitycode,
                      claimsoption,
                      verificationcode
                      )
        if (captcha is not None and 'guess' in self._data):
            self._data['guess'] = captcha.encode('utf-8')
        if (securitycode is not None and 'otpCode' in self._data):
            self._data['otpCode'] = securitycode.encode('utf-8')
            self._data['rememberDevice'] = ""
        if (claimsoption is not None and 'option' in self._data):
            self._data['option'] = claimsoption.encode('utf-8')
        if (verificationcode is not None and 'code' in self._data):
            self._data['code'] = verificationcode.encode('utf-8')
        self._session.headers['Content-Type'] = ("application/x-www-form-"
                                                 "urlencoded; charset=utf-8")
        self._data.pop('', None)

        if self._debug:
            _LOGGER.debug("Cookies: %s", self._session.cookies)
            _LOGGER.debug("Submit Form Data: %s", self._data)
            _LOGGER.debug("Header: %s", self._session.headers)

        # submit post request with username/password and other needed info
        post_resp = self._session.post(site, data=self._data)
        self._session.headers['Referer'] = site

        self._lastreq = post_resp
        if self._debug:
            with open(self._debugpost, mode='wb') as localfile:
                localfile.write(post_resp.content)

        post_soup = BeautifulSoup(post_resp.content, 'html.parser')

        login_tag = post_soup.find('form', {'name': 'signIn'})
        captcha_tag = post_soup.find(id="auth-captcha-image")

        # another login required and no captcha request? try once more.
        # This is a necessary hack as the first attempt always fails.
        # TODO: Figure out how to remove this hack pylint: disable=fixme

        if (login_tag is not None and captcha_tag is None):
            login_url = login_tag.get("action")
            _LOGGER.debug("Performing second login to: %s",
                          login_url)
            post_resp = self._session.post(login_url,
                                           data=self._data)
            if self._debug:
                with open(self._debugpost, mode='wb') as localfile:
                    localfile.write(post_resp.content)
            post_soup = BeautifulSoup(post_resp.content, 'html.parser')
            login_tag = post_soup.find('form', {'name': 'signIn'})
            captcha_tag = post_soup.find(id="auth-captcha-image")

        securitycode_tag = post_soup.find(id="auth-mfa-otpcode")
        errorbox = (post_soup.find(id="auth-error-message-box")
                    if post_soup.find(id="auth-error-message-box") else
                    post_soup.find(id="auth-warning-message-box"))
        claimspicker_tag = post_soup.find('form', {'name': 'claimspicker'})
        verificationcode_tag = post_soup.find('form', {'action': 'verify'})

        # pull out Amazon error message

        if errorbox:
            error_message = errorbox.find('h4').string
            for list_item in errorbox.findAll('li'):
                error_message += list_item.find('span').string
            _LOGGER.debug("Error message: %s", error_message)
            status['error_message'] = error_message

        if captcha_tag is not None:
            _LOGGER.debug("Captcha requested")
            status['captcha_required'] = True
            status['captcha_image_url'] = captcha_tag.get('src')
            self._data = self.get_inputs(post_soup)

        elif securitycode_tag is not None:
            _LOGGER.debug("2FA requested")
            status['securitycode_required'] = True
            self._data = self.get_inputs(post_soup, {'id': 'auth-mfa-form'})

        elif claimspicker_tag is not None:
            claims_message = ""
            options_message = ""
            for div in claimspicker_tag.findAll('div', 'a-row'):
                claims_message += "{}\n".format(div.string)
            for label in claimspicker_tag.findAll('label'):
                value = (label.find('input')['value']) if label.find(
                    'input') else ""
                message = (label.find('span').string) if label.find(
                    'span') else ""
                valuemessage = ("Option: {} = `{}`.\n".format(
                    value, message)) if value != "" else ""
                options_message += valuemessage
            _LOGGER.debug("Verification method requested: %s, %s",
                          claims_message,
                          options_message)
            status['claimspicker_required'] = True
            status['claimspicker_message'] = options_message
            self._data = self.get_inputs(post_soup, {'name': 'claimspicker'})
        elif verificationcode_tag is not None:
            _LOGGER.debug("Verification code requested:")
            status['verificationcode_required'] = True
            self._data = self.get_inputs(post_soup, {'action': 'verify'})
        elif login_tag is not None:
            login_url = login_tag.get("action")
            _LOGGER.debug("Another login requested to: %s", login_url)
            status['login_failed'] = True

        else:
            _LOGGER.debug("Captcha/2FA not requested; confirming login.")
            if self.test_loggedin():
                _LOGGER.debug("Login confirmed; saving cookie to %s",
                              self._cookiefile)
                status['login_successful'] = True
                with open(self._cookiefile, 'wb') as myfile:
                    try:
                        pickle.dump(self._session.cookies, myfile)
                    except OSError as ex:
                        template = ("An exception of type {0} occurred."
                                    " Arguments:\n{1!r}")
                        message = template.format(type(ex).__name__, ex.args)
                        _LOGGER.debug(
                            "Error saving pickled cookie to %s: %s",
                            self._cookiefile,
                            message)
            else:
                _LOGGER.debug("Login failed; check credentials")
                status['login_failed'] = True

        self.status = status
