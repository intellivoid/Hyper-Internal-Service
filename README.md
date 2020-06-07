# Hyper Internal Service

Hyper Internal Service is a internal async HTTP client/server
allowing for different internal components to communicate with
each other using various interchangeable data formats.


## Installation

```shell script
sudo -H make install
```

or 
```shell script
python3 -m pip install -Ur dev_requirements.txt
python3 setup.py install
```

## Example Server

```python
from hyper_internal_service import web


async def handle(request):
    name = request.match_info.get("name", "Anonymous")
    text = "Hello, " + name
    return web.Response(text=text)


async def wshandle(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            await ws.send_str("Hello, {}".format(msg.data))
        elif msg.type == web.WSMsgType.BINARY:
            await ws.send_bytes(msg.data)
        elif msg.type == web.WSMsgType.CLOSE:
            break

    return ws


app = web.Application()
app.add_routes([web.get("/", handle),
                web.get("/echo", wshandle),
                web.get("/{name}", handle)])

web.run_app(app)
```


## Example Client

```python
import asyncio
import hyper_internal_service


async def fetch(session):
    print('Query http://httpbin.org/get')
    async with session.get(
            'http://httpbin.org/get') as resp:
        print(resp.status)
        data = await resp.json()
        print(data)


async def go():
    async with hyper_internal_service.ClientSession() as session:
        await fetch(session)


loop = asyncio.get_event_loop()
loop.run_until_complete(go())
loop.close()
```