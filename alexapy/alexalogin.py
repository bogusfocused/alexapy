#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Python Package for controlling Alexa devices (echo dot, etc) programmatically.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""

from typing import Any, Callable, cast, Dict, List, Optional, Text, Tuple, Union  # noqa pylint: disable=unused-import

import logging

import aiohttp
from bs4 import BeautifulSoup
from yarl import URL

_LOGGER = logging.getLogger(__name__)


class AlexaLogin():
    # pylint: disable=too-many-instance-attributes
    """Class to handle login connection to Alexa. This class will not reconnect.

    Args:
    url (string): Localized Amazon domain (e.g., amazon.com)
    email (string): Amazon login account
    password (string): Password for Amazon login account
    outputpath (function): Local path with write access for storing files
    debug (boolean): Enable additional debugging including debug file creation

    """

    def __init__(self,
                 url: Text,
                 email: Text,
                 password: Text,
                 outputpath: Callable[[Text], Text],
                 debug: bool = False) -> None:
        # pylint: disable=too-many-arguments
        """Set up initial connection and log in."""
        import ssl
        import certifi
        prefix: Text = "alexa_media"
        self._url: Text = url
        self._email: Text = email
        self._password: Text = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._ssl = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, cafile=certifi.where()
        )
        self._cookies: Optional[Dict[Text, Text]] = {}
        self._headers: Dict[Text, Text] = {}
        self._data: Optional[Dict[Text, Text]] = None
        self.status: Optional[Dict[Text, Union[Text, bool]]] = {}
        self._cookiefile: Text = outputpath("{}.{}.pickle".format(prefix,
                                                                  email))
        self._debugpost: Text = outputpath("{}{}post.html".format(prefix,
                                                                  email))
        self._debugget: Text = outputpath("{}{}get.html".format(prefix,
                                                                email))
        self._lastreq: Optional[aiohttp.ClientResponse] = None
        self._debug: bool = debug
        self._links: Optional[Dict[Text, Tuple[Text, Text]]] = {}
        self._options: Optional[Dict[Text, Text]] = {}

    @property
    def email(self) -> Text:
        """Return email for this Login."""
        return self._email

    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        """Return session for this Login."""
        return self._session

    @property
    def url(self) -> Text:
        """Return session for this Login."""
        return self._url

    @property
    def links(self) -> Text:
        """Return string list of links from last page for this Login."""
        result = ""
        assert self._links is not None
        for key, value in self._links.items():
            result += "link{}:{}\n".format(key, value[0])
        return result

    async def login_with_cookie(self) -> None:
        """Attempt to login after loading cookie."""
        import pickle
        import aiofiles
        from requests.cookies import RequestsCookieJar
        cookies: Optional[RequestsCookieJar] = None
        if self._cookiefile:
            try:
                _LOGGER.debug(
                    "Trying to load cookie from file %s", self._cookiefile)
                async with aiofiles.open(self._cookiefile, 'rb') as myfile:
                    cookies = pickle.loads(await myfile.read())
                    _LOGGER.debug("cookie loaded: %s %s",
                                  type(cookies),
                                  cookies)
                    # escape extra quote marks from  Requests cookie
                    if isinstance(cookies,
                                  RequestsCookieJar):
                        self._cookies = cookies.get_dict()
                        assert self._cookies is not None
                        for key, value in cookies.items():
                            _LOGGER.debug('Key: "%s", Value: "%s"',
                                          key,
                                          value)
                            self._cookies[str(key)] = value.strip('\"')
                    else:
                        self._cookies = cookies
            except (OSError, EOFError, pickle.UnpicklingError) as ex:
                template = ("An exception of type {0} occurred."
                            " Arguments:\n{1!r}")
                message = template.format(type(ex).__name__, ex.args)
                _LOGGER.debug(
                    "Error loading pickled cookie from %s: %s",
                    self._cookiefile, message)

        await self.login(cookies=self._cookies)

    def reset_login(self) -> None:
        """Remove data related to existing login."""
        self._session = None
        self._cookies = None
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
    def get_inputs(cls,
                   soup: BeautifulSoup,
                   searchfield=None) -> Dict[str, str]:
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

    async def test_loggedin(self,
                            cookies: Union[Dict[str, str], None] = None
                            ) -> bool:
        """Function that will test the connection is logged in.

        Tests:
        - Attempts to get authenticaton and compares to expected login email
        Returns false if unsuccesful getting json or the emails don't match
        - Checks for existence of csrf cookie
        Returns false if no csrf found; necessary to issue commands
        """
        self._create_session()
        if self._debug:
            from json import dumps
            _LOGGER.debug("Testing whether logged in to alexa.%s",
                          self._url)
            _LOGGER.debug("Cookies: %s", dumps(self._cookies))
            _LOGGER.debug("Header: %s", dumps(self._headers))
        if not cookies:
            cookies = {}
        else:
            try:
                cookies['csrf']
            except KeyError as ex:
                _LOGGER.error(("Login successful, but AlexaLogin session is "
                               "missing required token: %s "
                               "please try to relogin but if this persists "
                               "this is unrecoverable, please report"),
                              ex)
                self.reset_login()
                return False
            self._cookies = cookies
        assert self._session is not None
        get_resp = await self._session.get('https://alexa.' + self._url +
                                           '/api/bootstrap',
                                           cookies=self._cookies,
                                           ssl=self._ssl
                                           )
        from simplejson import JSONDecodeError as SimpleJSONDecodeError
        from json import JSONDecodeError
        from aiohttp.client_exceptions import ContentTypeError
        try:
            json = await get_resp.json()
            email = json['authentication']['customerEmail']
        except (JSONDecodeError, SimpleJSONDecodeError,
                ContentTypeError) as ex:
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

    def _create_session(self) -> None:
        if not self._session:
            #  initiate session

            self._session = aiohttp.ClientSession()

            #  define session headers
            self._headers = {
                'User-Agent': ('Mozilla/5.0 (Windows NT 6.3; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/68.0.3440.106 Safari/537.36'),
                'Accept': ('text/html,application/xhtml+xml, '
                           'application/xml;q=0.9,*/*;q=0.8'),
                'Accept-Language': '*'
            }

    def _prepare_cookies_from_session(self, site: URL) -> None:
        """Update self._cookies from aiohttp session."""
        assert self._session is not None
        from http.cookies import BaseCookie
        cookies: BaseCookie = \
            self._session.cookie_jar.filter_cookies(URL(site))
        assert self._cookies is not None
        for _, cookie in cookies.items():
            # _LOGGER.debug('Key: "%s", Value: "%s"' %
            #               (cookie.key, cookie.value))
            self._cookies[cookie.key] = cookie.value

    async def login(self,
                    cookies: Optional[Dict[Text, Text]] = None,
                    data: Optional[Dict[Text, Optional[Text]]] = None) -> None:
        # pylint: disable=too-many-branches,too-many-locals,
        # pylint: disable=too-many-statements
        """Login to Amazon."""
        data = data or {}
        if (cookies is not None and await self.test_loggedin(cookies)):
            _LOGGER.debug("Using cookies to log in")
            self.status = {}
            self.status['login_successful'] = True
            _LOGGER.debug("Log in successful with cookies")
            return
        _LOGGER.debug("No valid cookies for log in; using credentials")
        #  site = 'https://www.' + self._url + '/gp/sign-in.html'
        #  use alexa site instead
        site: Text = 'https://alexa.' + self._url
        self._create_session()
        assert self._session is not None
        #  This will process links which is used for debug only to force going
        #  to other links.  Warning, chrome will cache any link parameters
        #  breaking the configuration flow until refresh on browser.
        digit = None
        for datum, value in data.items():
            if (value and str(value).startswith('link') and len(value) > 4 and
                    value[4:].isdigit()):
                digit = str(value[4:])
                _LOGGER.debug("Found link selection %s in %s ", digit, datum)
                assert self._links is not None
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
            assert self._lastreq is not None
            site = str(self._lastreq.url)
            _LOGGER.debug("Loaded last request to %s ", site)
            resp = self._lastreq
        else:
            resp = await self._session.get(site,
                                           cookies=self._cookies,
                                           headers=self._headers,
                                           ssl=self._ssl)
            self._lastreq = resp
            if resp.history:
                _LOGGER.debug("Get to %s was redirected to %s",
                              site,
                              resp.url)
                self._headers['Referer'] = str(resp.url)
            else:
                _LOGGER.debug("Get to %s was not redirected", site)
                self._headers['Referer'] = str(site)
        html: Text = await resp.text()
        if self._debug:
            import aiofiles
            async with aiofiles.open(self._debugget, mode='wb') as localfile:
                await localfile.write(await resp.read())

        self._prepare_cookies_from_session(URL(site))
        site = await self._process_page(html, site)
        missing_params = self._populate_data(site, data)
        if self._debug:
            from json import dumps
            _LOGGER.debug("Missing params: %s", missing_params)
            _LOGGER.debug("Cookies: %s", dumps(self._cookies))
            _LOGGER.debug("Submit Form Data: %s", dumps(self._data))
            _LOGGER.debug("Header: %s", dumps(self._headers))

        # submit post request with username/password and other needed info
        if not missing_params:
            post_resp = await self._session.post(site,
                                                 data=self._data,
                                                 cookies=self._cookies,
                                                 headers=self._headers,
                                                 ssl=self._ssl)
            self._headers['Referer'] = str(site)
            self._lastreq = post_resp
            if self._debug:
                import aiofiles
                async with aiofiles.open(self._debugpost,
                                         mode='wb') as localfile:
                    await localfile.write(await post_resp.read())
            self._prepare_cookies_from_session(URL(site))
            site = await self._process_page(await post_resp.text(), site)

    async def _process_page(self, html: str, site: Text) -> Text:
        # pylint: disable=too-many-branches,too-many-locals,
        # pylint: disable=too-many-statements
        """Process html to set login.status and find form post url."""
        def find_links() -> None:
            links = {}
            if links_tag:
                index = 0
                for link in links_tag:
                    if not link.string:
                        continue
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

        _LOGGER.debug("Processing %s", site)
        soup: BeautifulSoup = BeautifulSoup(html, 'html.parser')

        status: Dict[Text, Union[Text, bool]] = {}

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
        form_tag = soup.find('form')
        if self._debug:
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
                valuemessage = ("* **`{}`**:\t `{}`.\n".format(
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
            if await self.test_loggedin(cookies=self._cookies):
                _LOGGER.debug("Login confirmed; saving cookie to %s",
                              self._cookiefile)
                status['login_successful'] = True
                self._prepare_cookies_from_session(URL(site))
                _LOGGER.debug("Saving cookie: %s", self._cookies)
                with open(self._cookiefile, 'wb') as myfile:
                    import pickle
                    try:
                        pickle.dump(self._cookies, myfile)
                    except OSError as ex:
                        template = ("An exception of type {0} occurred."
                                    " Arguments:\n{1!r}")
                        message = template.format(type(ex).__name__, ex.args)
                        _LOGGER.debug(
                            "Error saving pickled cookie to %s: %s",
                            self._cookiefile,
                            message)
                #  remove extraneous Content-Type to avoid 500 errors
                self._headers.pop('Content-Type', None)

            else:
                _LOGGER.debug("Login failed; check credentials")
                status['login_failed'] = True
                assert self._data is not None
                if '' in self._data.values():
                    missing = [k for (k, v) in self._data.items() if v == '']
                    _LOGGER.debug("If credentials correct, please report"
                                  " these missing values: %s", missing)
        self.status = status
        # determine post url
        if form_tag:
            formsite: Text = form_tag.get('action')
            if formsite and formsite == 'verify':
                import re
                search_results = re.search(r'(.+)/(.*)',
                                           site)
                assert search_results is not None
                site = search_results.groups()[0] + "/verify"
                _LOGGER.debug("Found post url to verify; converting to %s",
                              site)
            elif formsite:
                site = formsite
                _LOGGER.debug("Found post url to %s",
                              site)
        return site

    def _populate_data(self,
                       site: Text,
                       data: Dict[str, Optional[str]]) -> bool:
        """Populate self._data with info from data."""
        # pull data from configurator
        captcha: Optional[Text] = (None if 'captcha' not in data
                                   else data['captcha'])
        securitycode: Optional[Text] = (None if 'securitycode' not in data
                                        else data['securitycode'])
        claimsoption: Optional[Text] = (None if 'claimsoption' not in data
                                        else data['claimsoption'])
        authopt: Optional[Text] = (None if 'authselectoption' not in data
                                   else data['authselectoption'])
        verificationcode: Optional[Text] = (None if 'verificationcode' not in
                                            data
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
            if "email" in self._data and self._data['email'] == "":
                self._data['email'] = self._email
            if "password" in self._data and self._data['password'] == "":
                self._data['password'] = self._password
            if "rememberMe" in self._data:
                self._data['rememberMe'] = "true"
            if (captcha is not None and 'guess' in self._data):
                self._data['guess'] = captcha
            if (securitycode is not None and 'otpCode' in self._data):
                self._data['otpCode'] = securitycode
                self._data['rememberDevice'] = "True"
            if (claimsoption is not None and 'option' in self._data):
                self._data['option'] = claimsoption
            if (authopt is not None and 'otpDeviceContext' in self._data):
                assert self._options is not None
                self._data['otpDeviceContext'] = self._options[authopt]
            if (verificationcode is not None and 'code' in self._data):
                self._data['code'] = verificationcode
            self._data.pop('', None)  # remove '' key
            return '' in self._data.values()  # test if unfilled values
        return False
