# alexapy

[![pipeline status](https://gitlab.com/keatontaylor/alexapy/badges/master/pipeline.svg)](https://gitlab.com/keatontaylor/alexapy/commits/master)

Python Package for controlling Alexa devices (echo dot, etc) programmatically. This was originally designed for [alexa_media_player](https://github.com/custom-components/alexa_media_player) a custom_component for [Home Assistant](https://www.home-assistant.io/).

**NOTE:** Alexa has no official API; therefore, this library may stop
working at any time without warning.

# Credits
Originally inspired by [this blog](https://blog.loetzimmer.de/2017/10/amazon-alexa-hort-auf-die-shell-echo.html) [(GitHub)](https://github.com/thorsten-gehrig/alexa-remote-control).
Additional scaffolding from [simplisafe-python](https://github.com/bachya/simplisafe-python)

# Contributing

1.  [Check for open features/bugs](https://gitlab.com/keatontaylor/alexapy/issues)
  or [initiate a discussion on one](https://gitlab.com/keatontaylor/alexapy/issues/new).
2.  [Fork the repository](https://gitlab.com/keatontaylor/alexapy/forks/new).
3.  Install the dev environment: `make init`.
4.  Enter the virtual environment: `pipenv shell`
5.  Code your new feature or bug fix.
6.  Write a test that covers your new functionality.
7.  Update `README.md` with any new documentation.
8.  Run tests and ensure 100% code coverage for your contribution: `make coverage`
9.  Ensure you have no linting errors: `make lint`
10. Ensure you have typed your code correctly: `make typing`
11. Add yourself to `AUTHORS.md`.
12. Submit a pull request!

# License
[Apache-2.0](LICENSE). By providing a contribution, you agree the contribution is licensed under Apache-2.0.
