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
        self._links = {}
        self._options = {}

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

    @property
    def links(self):
        """Return string list of links from last page for this Login."""
        result = ""
        for key, value in self._links.items():
            result += "link{}:{}\n".format(key, value[0])
        return result

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
            except (OSError, EOFError) as ex:
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
        self._links = {}
        self._options = {}
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
        if not form:
            form = soup.find('form')
        for field in form.find_all('input'):
            try:
                data[field['name']] = ""
                if field['type'] and field['type'] == 'hidden':
                    data[field['name']] = field['value']
            except BaseException:  # pylint: disable=broad-except
                pass
        return data

    def test_loggedin(self, cookies=None):
        """Function that will test the connection is logged in.

        Tests:
        - Attempts to get authenticaton and compares to expected login email
        Returns false if unsuccesful getting json or the emails don't match
        - Checks for existence of csrf cookie
        Returns false if no csrf found; necessary to issue commands
        """
        self._create_session()
        if cookies:
            self._session.cookies = cookies
        try:
            self._session.cookies.get_dict()['csrf']
        except KeyError as ex:
            _LOGGER.error(("Login successful, but AlexaLogin session is "
                           "missing required token: %s "
                           "please try to relogin once but if this persists "
                           "this is an unrecoverable error, please report"),
                          ex)
            self.reset_login()
            return False
        get_resp = self._session.get('https://alexa.' + self._url +
                                     '/api/bootstrap')
        # with open(self._debugget, mode='wb') as localfile:
        #     localfile.write(get_resp.content)

        from simplejson import JSONDecodeError
        try:
            email = get_resp.json()['authentication']['customerEmail']
        except (JSONDecodeError) as ex:
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

    def _create_session(self):
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
                'Accept-Language': '*',
                'Content-Type': ('application/x-www-form-'
                                 'urlencoded; charset=utf-8')
            }

    def login(self, cookies=None, data=None):
        # pylint: disable=too-many-branches,too-many-locals,
        # pylint: disable=too-many-statements
        """Login to Amazon."""
        data = data or {}
        if (cookies is not None and self.test_loggedin(cookies)):
            _LOGGER.debug("Using cookies to log in")
            self.status = {}
            self.status['login_successful'] = True
            _LOGGER.debug("Log in successful with cookies")
            return
        _LOGGER.debug("No valid cookies for log in; using credentials")
        #  site = 'https://www.' + self._url + '/gp/sign-in.html'
        #  use alexa site instead
        site = 'https://alexa.' + self._url
        self._create_session()

        #  This will process links which is used for debug only to force going
        #  to other links.  Warning, chrome will cache any link parameters
        #  breaking the configuration flow until refresh on browser.
        digit = None
        for datum, value in data.items():
            if (value and value.startswith('link') and len(value) > 4 and
                    value[4:].isdigit()):
                digit = str(value[4:])
                _LOGGER.debug("Found link selection %s in %s ", digit, datum)
                if self._links.get(digit):
                    (text, site) = self._links[digit]
                    data[datum] = None
                    _LOGGER.debug("Going to link with text: %s href: %s ",
                                  text,
                                  site)
                    _LOGGER.debug("%s reset to %s ",
                                  datum,
                                  data[datum])
        if not digit and self._lastreq is not None:
            site = self._lastreq.url
            _LOGGER.debug("Loaded last request to %s ", site)
            resp = self._lastreq
            html = self._lastreq.text
            from bs4 import BeautifulSoup
            #  get BeautifulSoup object of the html of the login page
            soup = BeautifulSoup(html, 'html.parser')
            site = soup.find('form').get('action')
            if site is None or site == "":
                site = self._lastreq.url
            elif site == 'verify':
                import re
                site = re.search(r'(.+)/(.*)',
                                 self._lastreq.url).groups()[0] + "/verify"
        else:
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

        self._process_page(html, site)
        missing_params = self._populate_data(site, data)
        if self._debug:
            _LOGGER.debug("Cookies: %s", self._session.cookies)
            _LOGGER.debug("Submit Form Data: %s", self._data)
            _LOGGER.debug("Header: %s", self._session.headers)

        # submit post request with username/password and other needed info
        if not missing_params:
            post_resp = self._session.post(site, data=self._data)
            self._session.headers['Referer'] = site

            self._lastreq = post_resp
            if self._debug:
                with open(self._debugpost, mode='wb') as localfile:
                    localfile.write(post_resp.content)
            self._process_page(post_resp.text, site)

    def _process_page(self, html, site):
        # pylint: disable=too-many-branches,too-many-locals,
        # pylint: disable=too-many-statements

        def find_links():
            links = {}
            if links_tag:
                index = 0
                for link in links_tag:
                    string = link.string.strip()
                    href = link['href']
                    # _LOGGER.debug("Found link: %s <%s>",
                    #               string,
                    #               href)
                    if href.startswith('/'):
                        links[str(index)] = (string,
                                             ('https://alexa.' + self._url
                                              + href))
                        index += 1
                    elif href.startswith('http'):
                        links[str(index)] = (string,
                                             href)
                        index += 1
                _LOGGER.debug("Links: %s",
                              links)
            self._links = links

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        status = {}

        #  Find tags to determine which path
        login_tag = soup.find('form', {'name': 'signIn'})
        captcha_tag = soup.find(id="auth-captcha-image")
        securitycode_tag = soup.find(id="auth-mfa-otpcode")
        errorbox = (soup.find(id="auth-error-message-box")
                    if soup.find(id="auth-error-message-box") else
                    soup.find(id="auth-warning-message-box"))
        claimspicker_tag = soup.find('form', {'name': 'claimspicker'})
        authselect_tag = soup.find('form',
                                   {'id': 'auth-select-device-form'})
        verificationcode_tag = soup.find('form', {'action': 'verify'})
        links_tag = soup.findAll('a', href=True)
        find_links()

        # pull out Amazon error message

        if errorbox:
            error_message = errorbox.find('h4').string
            for list_item in errorbox.findAll('li'):
                error_message += list_item.find('span').string
            _LOGGER.debug("Error message: %s", error_message)
            status['error_message'] = error_message

        if login_tag and not captcha_tag:
            _LOGGER.debug("Found standard login page")
            #  scrape login page to get all the inputs required for login
            self._data = self.get_inputs(soup, {'name': 'signIn'})
            formsite = soup.find('form').get('action')
            site = formsite if formsite else site
        elif captcha_tag is not None:
            _LOGGER.debug("Captcha requested")
            status['captcha_required'] = True
            status['captcha_image_url'] = captcha_tag.get('src')
            self._data = self.get_inputs(soup)

        elif securitycode_tag is not None:
            _LOGGER.debug("2FA requested")
            status['securitycode_required'] = True
            self._data = self.get_inputs(soup, {'id': 'auth-mfa-form'})

        elif claimspicker_tag is not None:
            claims_message = ""
            options_message = ""
            for div in claimspicker_tag.findAll('div', 'a-row'):
                claims_message += "{}\n".format(div.text)
            for label in claimspicker_tag.findAll('label'):
                value = (label.find('input')['value']).strip() if label.find(
                    'input') else ""
                message = (label.find('span').string).strip() if label.find(
                    'span') else ""
                valuemessage = ("Option: {} = `{}`.\n".format(
                    value, message)) if value != "" else ""
                options_message += valuemessage
            _LOGGER.debug("Verification method requested: %s, %s",
                          claims_message,
                          options_message)
            status['claimspicker_required'] = True
            status['claimspicker_message'] = options_message
            self._data = self.get_inputs(soup, {'name': 'claimspicker'})
        elif authselect_tag is not None:
            self._options = {}
            index = 0
            authselect_message = ""
            authoptions_message = ""
            for div in soup.findAll('div', 'a-box-inner'):
                if div.find('p'):
                    authselect_message += "{}\n".format(div.find('p').string)
            for label in authselect_tag.findAll('label'):
                value = (label.find('input')['value']).strip() if label.find(
                    'input') else ""
                message = (label.find('span').string).strip() if label.find(
                    'span') else ""
                valuemessage = ("{}:\t{}\n".format(
                    index, message)) if value != "" else ""
                authoptions_message += valuemessage
                self._options[str(index)] = value
                index += 1
            _LOGGER.debug("OTP method requested: %s%s",
                          authselect_message,
                          authoptions_message)
            status['authselect_required'] = True
            status['authselect_message'] = authoptions_message
            self._data = self.get_inputs(soup,
                                         {'id': 'auth-select-device-form'})
        elif verificationcode_tag is not None:
            _LOGGER.debug("Verification code requested:")
            status['verificationcode_required'] = True
            self._data = self.get_inputs(soup, {'action': 'verify'})
        else:
            _LOGGER.debug("Captcha/2FA not requested; confirming login.")
            if self.test_loggedin():
                _LOGGER.debug("Login confirmed; saving cookie to %s",
                              self._cookiefile)
                status['login_successful'] = True
                with open(self._cookiefile, 'wb') as myfile:
                    import pickle
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
                #  remove extraneous Content-Type to avoid 500 errors
                self._session.headers.pop('Content-Type', None)

            else:
                _LOGGER.debug("Login failed; check credentials")
                status['login_failed'] = True
                if '' in self._data.values():
                    missing = [k for (k, v) in self._data.items() if v == '']
                    _LOGGER.debug("If credentials correct, please report"
                                  " these missing values: %s", missing)
        self.status = status

    def _populate_data(self, site, data):
        """Populate self._data with info from data."""
        # pull data from configurator
        captcha = None if 'captcha' not in data else data['captcha']
        securitycode = (None if 'securitycode' not in data
                        else data['securitycode'])
        claimsoption = (None if 'claimsoption' not in data
                        else data['claimsoption'])
        authopt = (None if 'authselectoption' not in data
                   else data['authselectoption'])
        verificationcode = (None if 'verificationcode' not in data
                            else data['verificationcode'])
        _LOGGER.debug(("Preparing post to %s Captcha: %s"
                       " SecurityCode: %s Claimsoption: %s "
                       " AuthSelectOption: %s VerificationCode: %s"),
                      site,
                      captcha,
                      securitycode,
                      claimsoption,
                      authopt,
                      verificationcode)

        #  add username and password to the data for post request
        #  check if there is an input field
        if self._data:
            if "email" in self._data:
                self._data['email'] = self._email.encode('utf-8')
            if "password" in self._data:
                self._data['password'] = self._password.encode('utf-8')
            if "rememberMe" in self._data:
                self._data['rememberMe'] = "true".encode('utf-8')
            if (captcha is not None and 'guess' in self._data):
                self._data['guess'] = captcha.encode('utf-8')
            if (securitycode is not None and 'otpCode' in self._data):
                self._data['otpCode'] = securitycode.encode('utf-8')
                self._data['rememberDevice'] = True
            if (claimsoption is not None and 'option' in self._data):
                self._data['option'] = claimsoption.encode('utf-8')
            if (authopt is not None and 'otpDeviceContext' in self._data):
                self._data['otpDeviceContext'] = self._options[authopt]
            if (verificationcode is not None and 'code' in self._data):
                self._data['code'] = verificationcode.encode('utf-8')
            self._data.pop('', None)  # remove '' key
            return '' in self._data.values()  # test if unfilled values
        return False
