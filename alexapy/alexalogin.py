import requests

class AlexaLogin():
    """Class to handle login connection to Alexa."""

    def __init__(self, url, email, password, hass, alexa_data):
        """Set up initial connection and log in."""
        import pickle
        self._url = url
        self._email = email
        self._password = password
        self._session = None
        self._data = None
        self.status = {}
        self._cookiefile = hass.config.path("{}.pickle".format(alexa_data))
        self._debugpost = hass.config.path("{}post.html".format(alexa_data))
        self._debugget = hass.config.path("{}get.html".format(alexa_data))

        cookies = None
        if (self._cookiefile):
            try:
                _LOGGER.debug(
                    "Fetching cookie from file {}".format(
                        self._cookiefile))
                with open(self._cookiefile, 'rb') as myfile:
                    cookies = pickle.load(myfile)
                    _LOGGER.debug("cookie loaded: {}".format(cookies))
            except Exception as ex:
                template = ("An exception of type {0} occurred."
                            " Arguments:\n{1!r}")
                message = template.format(type(ex).__name__, ex.args)
                _LOGGER.debug(
                    "Error loading pickled cookie from {}: {}".format(
                        self._cookiefile, message))

        self.login(cookies=cookies)

    def reset_login(self):
        """Remove data related to existing login."""
        self._session = None
        self._data = None
        self.status = {}

    def get_inputs(self, soup, searchfield={'name': 'signIn'}):
        """Parse soup for form with searchfield."""
        data = {}
        form = soup.find('form', searchfield)
        for field in form.find_all('input'):
            try:
                data[field['name']] = ""
                data[field['name']] = field['value']
            except:  # noqa: E722 pylint: disable=bare-except
                pass
        return data

    def test_loggedin(self, cookies=None):
        """Function that will test the connection is logged in.

        Attempts to get device list, and if unsuccessful login failed
        """
        if self._session is None:
            site = 'https://www.' + self._url + '/gp/sign-in.html'

            '''initiate session'''
            self._session = requests.Session()

            '''define session headers'''
            self._session.headers = {
                'User-Agent': ('Mozilla/5.0 (Windows NT 6.3; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/44.0.2403.61 Safari/537.36'),
                'Accept': ('text/html,application/xhtml+xml, '
                           'application/xml;q=0.9,*/*;q=0.8'),
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': site
            }
            self._session.cookies = cookies
        get_resp = self._session.get('https://alexa.' + self._url +
                                     '/api/devices-v2/device')
        # with open(self._debugget, mode='wb') as localfile:
        #     localfile.write(get_resp.content)

        try:
            from json.decoder import JSONDecodeError
            from simplejson import JSONDecodeError as SimpleJSONDecodeError
            # Need to catch both as Python 3.5 appears to use simplejson
        except ImportError:
            JSONDecodeError = ValueError
        try:
            get_resp.json()
        except (JSONDecodeError, SimpleJSONDecodeError) as ex:
            # ValueError is necessary for Python 3.5 for some reason
            template = ("An exception of type {0} occurred."
                        " Arguments:\n{1!r}")
            message = template.format(type(ex).__name__, ex.args)
            _LOGGER.debug("Not logged in: {}".format(message))
            return False
        _LOGGER.debug("Logged in.")
        return True

    def login(self, cookies=None, captcha=None, securitycode=None):
        """Login to Amazon."""
        from bs4 import BeautifulSoup
        import pickle

        if cookies is not None:
            _LOGGER.debug("Using cookies to log in")
            if self.test_loggedin(cookies):
                self.status = {}
                self.status['login_successful'] = True
                _LOGGER.debug("Log in successful with cookies")
                return
        else:
            _LOGGER.debug("No cookies for log in; using credentials")
        #  site = 'https://www.' + self._url + '/gp/sign-in.html'
        #  use alexa site instead
        site = 'https://alexa.' + self._url + '/api/devices-v2/device'
        if self._session is None:
            '''initiate session'''

            self._session = requests.Session()

            '''define session headers'''
            self._session.headers = {
                'User-Agent': ('Mozilla/5.0 (Windows NT 6.3; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/44.0.2403.61 Safari/537.36'),
                'Accept': ('text/html,application/xhtml+xml, '
                           'application/xml;q=0.9,*/*;q=0.8'),
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': site
            }

        if self._data is None:
            resp = self._session.get(site)
            html = resp.text
            '''get BeautifulSoup object of the html of the login page'''
            soup = BeautifulSoup(html, 'html.parser')
            '''scrape login page to get all the inputs required for login'''
            self._data = self.get_inputs(soup)
            site = soup.find('form', {'name': 'signIn'}).get('action')

        # _LOGGER.debug("Init Form Data: {}".format(self._data))

        '''add username and password to the data for post request'''
        '''check if there is an input field'''
        if "email" in self._data:
            self._data[u'email'] = self._email
        if "password" in self._data:
            self._data[u'password'] = self._password
        if "rememberMe" in self._data:
            self._data[u'rememberMe'] = "true"

        status = {}
        _LOGGER.debug("Captcha: {} SecurityCode: {}".format(captcha,
                                                            securitycode))
        if (captcha is not None and 'guess' in self._data):
            self._data[u'guess'] = captcha
        if (securitycode is not None and 'otpCode' in self._data):
            self._data[u'otpCode'] = securitycode
            self._data[u'rememberDevice'] = "true"
            self._data[u'mfaSubmit'] = "true"

        # _LOGGER.debug("Submit Form Data: {}".format(self._data))

        '''submit post request with username/password and other needed info'''
        post_resp = self._session.post(site, data=self._data)
        # with open(self._debugpost, mode='wb') as localfile:
        #     localfile.write(post_resp.content)

        post_soup = BeautifulSoup(post_resp.content, 'html.parser')

        captcha_tag = post_soup.find(id="auth-captcha-image")
        securitycode_tag = post_soup.find(id="auth-mfa-otpcode")
        login_tag = post_soup.find('form', {'name': 'signIn'})

        '''another login required? try once more. This appears necessary as
        the first login fails for alexa's login site for some reason
        '''
        if login_tag is not None:
            login_url = login_tag.get("action")
            _LOGGER.debug("Login requested again; retrying once: {}".format(
                login_url))
            post_resp = self._session.post(login_url,
                                           data=self._data)
            # with open(self._debugpost, mode='wb') as localfile:
            #     localfile.write(post_resp.content)
            post_soup = BeautifulSoup(post_resp.content, 'html.parser')
            captcha_tag = post_soup.find(id="auth-captcha-image")
            securitycode_tag = post_soup.find(id="auth-mfa-otpcode")

        if captcha_tag is not None:
            _LOGGER.debug("Captcha requested")
            status['captcha_required'] = True
            status['captcha_image_url'] = captcha_tag.get('src')
            self._data = self.get_inputs(post_soup)

        elif securitycode_tag is not None:
            _LOGGER.debug("2FA requested")
            status['securitycode_required'] = True
            self._data = self.get_inputs(post_soup, {'id': 'auth-mfa-form'})

        else:
            _LOGGER.debug("Captcha/2FA not requested; confirming login.")
            if self.test_loggedin():
                _LOGGER.debug("Login confirmed; saving cookie to {}".format(
                        self._cookiefile))
                status['login_successful'] = True
                with open(self._cookiefile, 'wb') as myfile:
                    try:
                        pickle.dump(self._session.cookies, myfile)
                    except Exception as ex:
                        template = ("An exception of type {0} occurred."
                                    " Arguments:\n{1!r}")
                        message = template.format(type(ex).__name__, ex.args)
                        _LOGGER.debug(
                            "Error saving pickled cookie to {}: {}".format(
                                self._cookiefile,
                                message))
            else:
                _LOGGER.debug("Login failed; check credentials")

        self.status = status
