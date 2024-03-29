import asyncio
import contextlib
import warnings
from collections.abc import Callable

import pytest

from hyper_internal_service.helpers import PY_37, isasyncgenfunction
from hyper_internal_service.web import Application

from .test_utils import (
    BaseTestServer,
    RawTestServer,
    TestClient,
    TestServer,
    loop_context,
    setup_test_loop,
    teardown_test_loop,
)
from .test_utils import unused_port as _unused_port

try:
    import uvloop
except ImportError:  # pragma: no cover
    uvloop = None

try:
    import tokio
except ImportError:  # pragma: no cover
    tokio = None


def pytest_addoption(parser):  # type: ignore
    parser.addoption(
        '--hyper_internal_service-fast', action='store_true', default=False,
        help='run tests faster by disabling extra checks')
    parser.addoption(
        '--hyper_internal_service-loop', action='store', default='pyloop',
        help='run tests with specific loop: pyloop, uvloop, tokio or all')
    parser.addoption(
        '--hyper_internal_service-enable-loop-debug', action='store_true', default=False,
        help='enable event loop debug mode')


def pytest_fixture_setup(fixturedef):  # type: ignore
    """
    Allow fixtures to be coroutines. Run coroutine fixtures in an event loop.
    """
    func = fixturedef.func

    if isasyncgenfunction(func):
        # async generator fixture
        is_async_gen = True
    elif asyncio.iscoroutinefunction(func):
        # regular async fixture
        is_async_gen = False
    else:
        # not an async fixture, nothing to do
        return

    strip_request = False
    if 'request' not in fixturedef.argnames:
        fixturedef.argnames += ('request',)
        strip_request = True

    def wrapper(*args, **kwargs):  # type: ignore
        request = kwargs['request']
        if strip_request:
            del kwargs['request']

        # if neither the fixture nor the test use the 'loop' fixture,
        # 'getfixturevalue' will fail because the test is not parameterized
        # (this can be removed someday if 'loop' is no longer parameterized)
        if 'loop' not in request.fixturenames:
            raise Exception(
                "Asynchronous fixtures must depend on the 'loop' fixture or "
                "be used in tests depending from it."
            )

        _loop = request.getfixturevalue('loop')

        if is_async_gen:
            # for async generators, we need to advance the generator once,
            # then advance it again in a finalizer
            gen = func(*args, **kwargs)

            def finalizer():  # type: ignore
                try:
                    return _loop.run_until_complete(gen.__anext__())
                except StopAsyncIteration:  # NOQA
                    pass

            request.addfinalizer(finalizer)
            return _loop.run_until_complete(gen.__anext__())
        else:
            return _loop.run_until_complete(func(*args, **kwargs))

    fixturedef.func = wrapper


@pytest.fixture
def fast(request):  # type: ignore
    """--fast config option"""
    return request.config.getoption('--hyper_internal_service-fast')


@pytest.fixture
def loop_debug(request):  # type: ignore
    """--enable-loop-debug config option"""
    return request.config.getoption('--hyper_internal_service-enable-loop-debug')


@contextlib.contextmanager
def _runtime_warning_context():  # type: ignore
    """
    Context manager which checks for RuntimeWarnings, specifically to
    avoid "coroutine 'X' was never awaited" warnings being missed.

    If RuntimeWarnings occur in the context a RuntimeError is raised.
    """
    with warnings.catch_warnings(record=True) as _warnings:
        yield
        rw = ['{w.filename}:{w.lineno}:{w.message}'.format(w=w)
              for w in _warnings
              if w.category == RuntimeWarning]
        if rw:
            raise RuntimeError('{} Runtime Warning{},\n{}'.format(
                len(rw),
                '' if len(rw) == 1 else 's',
                '\n'.join(rw)
            ))


@contextlib.contextmanager
def _passthrough_loop_context(loop, fast=False):  # type: ignore
    """
    setups and tears down a loop unless one is passed in via the loop
    argument when it's passed straight through.
    """
    if loop:
        # loop already exists, pass it straight through
        yield loop
    else:
        # this shadows loop_context's standard behavior
        loop = setup_test_loop()
        yield loop
        teardown_test_loop(loop, fast=fast)


def pytest_pycollect_makeitem(collector, name, obj):  # type: ignore
    """
    Fix pytest collecting for coroutines.
    """
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


def pytest_pyfunc_call(pyfuncitem):  # type: ignore
    """
    Run coroutines in an event loop instead of a normal function call.
    """
    fast = pyfuncitem.config.getoption("--hyper_internal_service-fast")
    if asyncio.iscoroutinefunction(pyfuncitem.function):
        existing_loop = pyfuncitem.funcargs.get('proactor_loop')\
            or pyfuncitem.funcargs.get('loop', None)
        with _runtime_warning_context():
            with _passthrough_loop_context(existing_loop, fast=fast) as _loop:
                testargs = {arg: pyfuncitem.funcargs[arg]
                            for arg in pyfuncitem._fixtureinfo.argnames}
                _loop.run_until_complete(pyfuncitem.obj(**testargs))

        return True


def pytest_generate_tests(metafunc):  # type: ignore
    if 'loop_factory' not in metafunc.fixturenames:
        return

    loops = metafunc.config.option.hyper_internal_service_loop
    avail_factories = {'pyloop': asyncio.DefaultEventLoopPolicy}

    if uvloop is not None:  # pragma: no cover
        avail_factories['uvloop'] = uvloop.EventLoopPolicy

    if tokio is not None:  # pragma: no cover
        avail_factories['tokio'] = tokio.EventLoopPolicy

    if loops == 'all':
        loops = 'pyloop,uvloop?,tokio?'

    factories = {}  # type: ignore
    for name in loops.split(','):
        required = not name.endswith('?')
        name = name.strip(' ?')
        if name not in avail_factories:  # pragma: no cover
            if required:
                raise ValueError(
                    "Unknown loop '%s', available loops: %s" % (
                        name, list(factories.keys())))
            else:
                continue
        factories[name] = avail_factories[name]
    metafunc.parametrize("loop_factory",
                         list(factories.values()),
                         ids=list(factories.keys()))


@pytest.fixture
def loop(loop_factory, fast, loop_debug):  # type: ignore
    """Return an instance of the event loop."""
    policy = loop_factory()
    asyncio.set_event_loop_policy(policy)
    with loop_context(fast=fast) as _loop:
        if loop_debug:
            _loop.set_debug(True)  # pragma: no cover
        asyncio.set_event_loop(_loop)
        yield _loop


@pytest.fixture
def proactor_loop():  # type: ignore
    if not PY_37:
        policy = asyncio.get_event_loop_policy()
        policy._loop_factory = asyncio.ProactorEventLoop  # type: ignore
    else:
        policy = asyncio.WindowsProactorEventLoopPolicy()  # type: ignore
        asyncio.set_event_loop_policy(policy)

    with loop_context(policy.new_event_loop) as _loop:
        asyncio.set_event_loop(_loop)
        yield _loop


@pytest.fixture
def unused_port(hyper_internal_service_unused_port):  # type: ignore # pragma: no cover
    warnings.warn("Deprecated, use hyper_internal_service_unused_port fixture instead",
                  DeprecationWarning,
                  stacklevel=2)
    return hyper_internal_service_unused_port


@pytest.fixture
def hyper_internal_service_unused_port():  # type: ignore
    """Return a port that is unused on the current host."""
    return _unused_port


@pytest.fixture
def hyper_internal_service_server(loop):  # type: ignore
    """Factory to create a TestServer instance, given an app.

    hyper_internal_service_server(app, **kwargs)
    """
    servers = []

    async def go(app, *, port=None, **kwargs):  # type: ignore
        server = TestServer(app, port=port)
        await server.start_server(loop=loop, **kwargs)
        servers.append(server)
        return server

    yield go

    async def finalize():  # type: ignore
        while servers:
            await servers.pop().close()

    loop.run_until_complete(finalize())


@pytest.fixture
def test_server(hyper_internal_service_server):  # type: ignore  # pragma: no cover
    warnings.warn("Deprecated, use hyper_internal_service_server fixture instead",
                  DeprecationWarning,
                  stacklevel=2)
    return hyper_internal_service_server


@pytest.fixture
def hyper_internal_service_raw_server(loop):  # type: ignore
    """Factory to create a RawTestServer instance, given a web handler.

    hyper_internal_service_raw_server(handler, **kwargs)
    """
    servers = []

    async def go(handler, *, port=None, **kwargs):  # type: ignore
        server = RawTestServer(handler, port=port)
        await server.start_server(loop=loop, **kwargs)
        servers.append(server)
        return server

    yield go

    async def finalize():  # type: ignore
        while servers:
            await servers.pop().close()

    loop.run_until_complete(finalize())


@pytest.fixture
def raw_test_server(hyper_internal_service_raw_server):  # type: ignore  # pragma: no cover
    warnings.warn("Deprecated, use hyper_internal_service_raw_server fixture instead",
                  DeprecationWarning,
                  stacklevel=2)
    return hyper_internal_service_raw_server


@pytest.fixture
def hyper_internal_service_client(loop):  # type: ignore
    """Factory to create a TestClient instance.

    hyper_internal_service_client(app, **kwargs)
    hyper_internal_service_client(server, **kwargs)
    hyper_internal_service_client(raw_server, **kwargs)
    """
    clients = []

    async def go(__param, *args, server_kwargs=None, **kwargs):  # type: ignore

        if (isinstance(__param, Callable) and  # type: ignore
                not isinstance(__param, (Application, BaseTestServer))):
            __param = __param(loop, *args, **kwargs)
            kwargs = {}
        else:
            assert not args, "args should be empty"

        if isinstance(__param, Application):
            server_kwargs = server_kwargs or {}
            server = TestServer(__param, loop=loop, **server_kwargs)
            client = TestClient(server, loop=loop, **kwargs)
        elif isinstance(__param, BaseTestServer):
            client = TestClient(__param, loop=loop, **kwargs)
        else:
            raise ValueError("Unknown argument type: %r" % type(__param))

        await client.start_server()
        clients.append(client)
        return client

    yield go

    async def finalize():  # type: ignore
        while clients:
            await clients.pop().close()

    loop.run_until_complete(finalize())


@pytest.fixture
def test_client(hyper_internal_service_client):  # type: ignore  # pragma: no cover
    warnings.warn("Deprecated, use hyper_internal_service_client fixture instead",
                  DeprecationWarning,
                  stacklevel=2)
    return hyper_internal_service_client
