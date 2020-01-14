#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  SPDX-License-Identifier: Apache-2.0
"""
Temporary fix of aiohttp/cookiejar until patch merged.

https://github.com/aio-libs/aiohttp/pull/4066
For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
import datetime
from http.cookies import Morsel, SimpleCookie  # noqa
from typing import Mapping  # noqa

from aiohttp.cookiejar import CookieJar
from aiohttp.helpers import is_ip_address
from aiohttp.typedefs import LooseCookies
from yarl import URL


class FixedCookieJar(CookieJar):
    # pylint: disable=too-many-branches
    """Fixed version of CookieJar that handles expired cookies."""

    def update_cookies(self,
                       cookies: LooseCookies,
                       response_url: URL = URL()) -> None:
        """Update cookies."""
        hostname = response_url.raw_host

        if not self._unsafe and is_ip_address(hostname):
            # Don't accept cookies from IPs
            return

        if isinstance(cookies, Mapping):
            cookies = cookies.items()  # type: ignore

        for name, cookie in cookies:
            if not isinstance(cookie, Morsel):
                tmp = SimpleCookie()  # type: SimpleCookie[str]
                tmp[name] = cookie  # type: ignore
                cookie = tmp[name]

            domain = cookie["domain"]

            # ignore domains with trailing dots
            if domain.endswith('.'):
                domain = ""
                del cookie["domain"]

            if not domain and hostname is not None:
                # Set the cookie's domain to the response hostname
                # and set its host-only-flag
                self._host_only_cookies.add((hostname, name))
                domain = cookie["domain"] = hostname

            if domain.startswith("."):
                # Remove leading dot
                domain = domain[1:]
                cookie["domain"] = domain

            if hostname and not self._is_domain_match(domain, hostname):
                # Setting cookies for different domains is not allowed
                continue

            path = cookie["path"]
            if not path or not path.startswith("/"):
                # Set the cookie's path to the response path
                path = response_url.path
                if not path.startswith("/"):
                    path = "/"
                else:
                    # Cut everything from the last slash to the end
                    path = "/" + path[1:path.rfind("/")]
                cookie["path"] = path

            max_age = cookie["max-age"]
            if max_age:
                try:
                    delta_seconds = int(max_age)
                    try:
                        max_age_expiration = (
                            datetime.datetime.now(datetime.timezone.utc) +
                            datetime.timedelta(seconds=delta_seconds))
                    except OverflowError:
                        max_age_expiration = self.MAX_TIME
                    self._expire_cookie(max_age_expiration,
                                        domain, name)
                except ValueError:
                    cookie["max-age"] = ""

            else:
                expires = cookie["expires"]
                if expires:
                    expire_time = self._parse_date(expires)
                    if expire_time:
                        self._expire_cookie(expire_time,
                                            domain, name)
                    else:
                        cookie["expires"] = ""

            self._cookies[domain][name] = cookie

        self._do_expiration()
