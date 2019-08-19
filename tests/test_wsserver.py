#!/usr/bin/env python

# This websocket server was used to determine the difference in websocket libs
# target the '/ws' endpoint without ssl, e.g., url = "ws://localhost:8080/ws"


from aiohttp import web
import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)


app = web.Application()


async def openfile(name: str = 'saved.pickle') -> dict:
    import aiofiles
    import pickle
    saved = {}
    try:
        async with aiofiles.open(name, 'rb') as myfile:
            saved = pickle.loads(await myfile.read())
            _LOGGER.debug("Loaded %s: %s",
                          name,
                          saved)
    except (OSError, EOFError) as ex:
        template = ("An exception of type {0} occurred."
                    " Arguments:\n{1!r}")
        message = template.format(type(ex).__name__, ex.args)
        _LOGGER.debug(
            "Error loading saved file: %s",
            message)
    return saved


def savefile(data: dict, name: str = 'saved.pickle') -> bool:
    import pickle
    saved = False
    with open(name, 'wb') as myfile:
        try:
            pickle.dump(data, myfile)
            saved = True
        except OSError as ex:
            template = ("An exception of type {0} occurred."
                        " Arguments:\n{1!r}")
            message = template.format(type(ex).__name__, ex.args)
            _LOGGER.debug(
                "Error saving %s: %s",
                name,
                message)
    return saved


async def websocket_handler(request):
    def test_value(cur_val, test_val):
        print(test_val)
        if cur_val in saved:
            assert(saved[cur_val] == test_val)
        else:
            saved[cur_val] = test_val

    saved = None
    saved = await openfile()
    if not saved:
        saved = {}
        save = True
    else:
        save = False
    test_value('headers', request.headers)
    test_value('cookies', request.cookies)
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    index = 0
    try:
        async for msg in ws:
            test_value(index, msg)
            if msg.type == aiohttp.WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
                else:
                    await ws.send_str(msg.data + '/answer')
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print('ws connection closed with exception %s' %
                      ws.exception())
            index += 1
        print('websocket connection closed')
    except KeyboardInterrupt:
        if save:
            savefile(saved)
    if save:
        savefile(saved)
    return ws

app.add_routes([web.get('/ws', websocket_handler)])

web.run_app(app)
