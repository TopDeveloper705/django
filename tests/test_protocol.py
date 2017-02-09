"""Tests for aiohttp/protocol.py"""

import asyncio
import zlib
from unittest import mock

import pytest

from aiohttp import hdrs, protocol


@pytest.fixture
def transport():
    transport = mock.Mock()

    def acquire(cb):
        cb(transport)

    transport.acquire = acquire
    transport.drain.return_value = ()
    return transport


compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
COMPRESSED = b''.join([compressor.compress(b'data'), compressor.flush()])


def test_start_request(transport):
    msg = protocol.Request(
        transport, 'GET', '/index.html', close=True)

    assert msg._transport is transport
    assert msg.closing
    assert msg.status_line == 'GET /index.html HTTP/1.1\r\n'


def test_start_response(transport):
    msg = protocol.Response(transport, 200, close=True)

    assert msg._transport is transport
    assert msg.status == 200
    assert msg.reason == "OK"
    assert msg.closing
    assert msg.status_line == 'HTTP/1.1 200 OK\r\n'


def test_start_response_with_reason(transport):
    msg = protocol.Response(transport, 333, close=True,
                            reason="My Reason")

    assert msg.status == 333
    assert msg.reason == "My Reason"
    assert msg.status_line == 'HTTP/1.1 333 My Reason\r\n'


def test_start_response_with_unknown_reason(transport):
    msg = protocol.Response(transport, 777, close=True)

    assert msg.status == 777
    assert msg.reason == "777"
    assert msg.status_line == 'HTTP/1.1 777 777\r\n'


def test_force_close(transport):
    msg = protocol.Response(transport, 200)
    assert not msg.closing
    msg.force_close()
    assert msg.closing


def test_force_chunked(transport):
    msg = protocol.Response(transport, 200)
    assert not msg.chunked
    msg.enable_chunking()
    assert msg.chunked


def test_keep_alive(transport):
    msg = protocol.Response(transport, 200, close=True)
    assert not msg.keep_alive()
    msg.keepalive = True
    assert msg.keep_alive()

    msg.force_close()
    assert not msg.keep_alive()


def test_keep_alive_http10(transport):
    msg = protocol.Response(transport, 200, http_version=(1, 0))
    assert not msg.keepalive
    assert not msg.keep_alive()

    msg = protocol.Response(transport, 200, http_version=(1, 1))
    assert msg.keepalive is None


def test_add_header(transport):
    msg = protocol.Response(transport, 200)
    assert [] == list(msg.headers)

    msg.add_header('content-type', 'plain/html')
    assert [('Content-Type', 'plain/html')] == list(msg.headers.items())


def test_add_header_with_spaces(transport):
    msg = protocol.Response(transport, 200)
    assert [] == list(msg.headers)

    msg.add_header('content-type', '  plain/html  ')
    assert [('Content-Type', 'plain/html')] == list(msg.headers.items())


def test_add_header_non_ascii(transport):
    msg = protocol.Response(transport, 200)
    assert [] == list(msg.headers)

    with pytest.raises(AssertionError):
        msg.add_header('тип-контента', 'текст/плейн')


def test_add_header_invalid_value_type(transport):
    msg = protocol.Response(transport, 200)
    assert [] == list(msg.headers)

    with pytest.raises(AssertionError):
        msg.add_header('content-type', {'test': 'plain'})

    with pytest.raises(AssertionError):
        msg.add_header(list('content-type'), 'text/plain')


def test_add_headers(transport):
    msg = protocol.Response(transport, 200)
    assert [] == list(msg.headers)

    msg.add_headers(('content-type', 'plain/html'))
    assert [('Content-Type', 'plain/html')] == list(msg.headers.items())


def test_add_headers_length(transport):
    msg = protocol.Response(transport, 200)
    assert msg.length is None

    msg.add_headers(('content-length', '42'))
    assert 42 == msg.length


def test_add_headers_upgrade(transport):
    msg = protocol.Response(transport, 200)
    assert not msg.upgrade

    msg.add_headers(('connection', 'upgrade'))
    assert msg.upgrade


def test_add_headers_upgrade_websocket(transport):
    msg = protocol.Response(transport, 200)
    msg.add_headers(('upgrade', 'test'))
    assert not msg.websocket
    assert [('Upgrade', 'test')] == list(msg.headers.items())

    msg = protocol.Response(transport, 200)
    msg.add_headers(('upgrade', 'websocket'))
    assert msg.websocket
    assert [('Upgrade', 'websocket')] == list(msg.headers.items())


def test_add_headers_connection_keepalive(transport):
    msg = protocol.Response(transport, 200)

    msg.add_headers(('connection', 'keep-alive'))
    assert [] == list(msg.headers)
    assert msg.keepalive

    msg.add_headers(('connection', 'close'))
    assert not msg.keepalive


def test_add_headers_hop_headers(transport):
    msg = protocol.Response(transport, 200)
    msg.HOP_HEADERS = (hdrs.TRANSFER_ENCODING,)

    msg.add_headers(('connection', 'test'), ('transfer-encoding', 't'))
    assert [] == list(msg.headers)


def test_default_headers_http_10(transport):
    msg = protocol.Response(transport, 200,
                            http_version=protocol.HttpVersion10)
    msg._add_default_headers()

    assert 'DATE' in msg.headers
    assert 'keep-alive' == msg.headers['CONNECTION']


def test_default_headers_http_11(transport):
    msg = protocol.Response(transport, 200)
    msg._add_default_headers()

    assert 'DATE' in msg.headers
    assert 'CONNECTION' not in msg.headers


def test_default_headers_server(transport):
    msg = protocol.Response(transport, 200)
    msg._add_default_headers()

    assert 'SERVER' in msg.headers


def test_default_headers_chunked(transport):
    msg = protocol.Response(transport, 200)
    msg._add_default_headers()

    assert 'TRANSFER-ENCODING' not in msg.headers

    msg = protocol.Response(transport, 200)
    msg.enable_chunking()
    msg.send_headers()

    assert 'TRANSFER-ENCODING' in msg.headers


def test_default_headers_connection_upgrade(transport):
    msg = protocol.Response(transport, 200)
    msg.upgrade = True
    msg._add_default_headers()

    assert msg.headers['Connection'] == 'Upgrade'


def test_default_headers_connection_close(transport):
    msg = protocol.Response(transport, 200)
    msg.force_close()
    msg._add_default_headers()

    assert msg.headers['Connection'] == 'close'


def test_default_headers_connection_keep_alive_http_10(transport):
    msg = protocol.Response(transport, 200,
                            http_version=protocol.HttpVersion10)
    msg.keepalive = True
    msg._add_default_headers()

    assert msg.headers['Connection'] == 'keep-alive'


def test_default_headers_connection_keep_alive_11(transport):
    msg = protocol.Response(transport, 200,
                            http_version=protocol.HttpVersion11)
    msg.keepalive = True
    msg._add_default_headers()

    assert 'Connection' not in msg.headers


def test_send_headers(transport):
    write = transport.write = mock.Mock()

    msg = protocol.Response(transport, 200)
    msg.add_headers(('content-type', 'plain/html'))
    assert not msg.is_headers_sent()

    msg.send_headers()

    content = b''.join([arg[1][0] for arg in list(write.mock_calls)])

    assert content.startswith(b'HTTP/1.1 200 OK\r\n')
    assert b'Content-Type: plain/html' in content
    assert msg.headers_sent
    assert msg.is_headers_sent()


def test_send_headers_non_ascii(transport):
    write = transport.write = mock.Mock()

    msg = protocol.Response(transport, 200)
    msg.add_headers(('x-header', 'текст'))
    assert not msg.is_headers_sent()

    msg.send_headers()

    content = b''.join([arg[1][0] for arg in list(write.mock_calls)])

    assert content.startswith(b'HTTP/1.1 200 OK\r\n')
    assert b'X-Header: \xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82' in content
    assert msg.headers_sent
    assert msg.is_headers_sent()


def test_send_headers_nomore_add(transport):
    msg = protocol.Response(transport, 200)
    msg.add_headers(('content-type', 'plain/html'))
    msg.send_headers()

    with pytest.raises(AssertionError):
        msg.add_header('content-type', 'plain/html')


def test_prepare_length(transport):
    msg = protocol.Response(transport, 200)
    msg.add_headers(('content-length', '42'))
    msg.send_headers()

    assert msg.length == 42


def test_prepare_chunked_force(transport):
    msg = protocol.Response(transport, 200)
    msg.enable_chunking()
    msg.add_headers(('content-length', '42'))
    msg.send_headers()
    assert msg.chunked


def test_prepare_chunked_no_length(transport):
    msg = protocol.Response(transport, 200)
    msg.send_headers()
    assert msg.chunked


def test_prepare_eof(transport):
    msg = protocol.Response(transport, 200, http_version=(1, 0))
    msg.send_headers()
    assert msg.length is None


def test_write_auto_send_headers(transport):
    msg = protocol.Response(transport, 200, http_version=(1, 0))
    msg.send_headers()
    msg.write(b'data1')
    assert msg.headers_sent


def test_write_payload_eof(transport):
    write = transport.write = mock.Mock()
    msg = protocol.Response(transport, 200, http_version=(1, 0))
    msg.send_headers()

    msg.write(b'data1')
    assert msg.headers_sent

    msg.write(b'data2')
    msg.write_eof()

    content = b''.join([c[1][0] for c in list(write.mock_calls)])
    assert b'data1data2' == content.split(b'\r\n\r\n', 1)[-1]


@asyncio.coroutine
def test_write_payload_chunked(transport):
    write = transport.write = mock.Mock()

    msg = protocol.Response(transport, 200)
    msg.enable_chunking()
    msg.send_headers()

    msg.write(b'data')
    yield from msg.write_eof()

    content = b''.join([c[1][0] for c in list(write.mock_calls)])
    assert b'4\r\ndata\r\n0\r\n\r\n' == content.split(b'\r\n\r\n', 1)[-1]


@asyncio.coroutine
def test_write_payload_chunked_multiple(transport):
    write = transport.write = mock.Mock()

    msg = protocol.Response(transport, 200)
    msg.enable_chunking()
    msg.send_headers()

    msg.write(b'data1')
    msg.write(b'data2')
    yield from msg.write_eof()

    content = b''.join([c[1][0] for c in list(write.mock_calls)])
    assert (b'5\r\ndata1\r\n5\r\ndata2\r\n0\r\n\r\n' ==
            content.split(b'\r\n\r\n', 1)[-1])


@asyncio.coroutine
def test_write_payload_length(transport):
    write = transport.write = mock.Mock()

    msg = protocol.Response(transport, 200)
    msg.add_headers(('content-length', '2'))
    msg.send_headers()

    msg.write(b'd')
    msg.write(b'ata')
    yield from msg.write_eof()

    content = b''.join([c[1][0] for c in list(write.mock_calls)])
    assert b'da' == content.split(b'\r\n\r\n', 1)[-1]


@asyncio.coroutine
def test_write_payload_chunked_filter(transport):
    write = transport.write = mock.Mock()

    msg = protocol.Response(transport, 200)
    msg.send_headers()

    msg.enable_chunking()
    msg.write(b'da')
    msg.write(b'ta')
    yield from msg.write_eof()

    content = b''.join([c[1][0] for c in list(write.mock_calls)])
    assert content.endswith(b'2\r\nda\r\n2\r\nta\r\n0\r\n\r\n')


@asyncio.coroutine
def test_write_payload_chunked_filter_mutiple_chunks(transport):
    write = transport.write = mock.Mock()
    msg = protocol.Response(transport, 200)
    msg.send_headers()

    msg.enable_chunking()
    msg.write(b'da')
    msg.write(b'ta')
    msg.write(b'1d')
    msg.write(b'at')
    msg.write(b'a2')
    yield from msg.write_eof()
    content = b''.join([c[1][0] for c in list(write.mock_calls)])
    assert content.endswith(
        b'2\r\nda\r\n2\r\nta\r\n2\r\n1d\r\n2\r\nat\r\n'
        b'2\r\na2\r\n0\r\n\r\n')


@asyncio.coroutine
def test_write_payload_deflate_compression(transport):
    write = transport.write = mock.Mock()
    msg = protocol.Response(transport, 200)
    msg.add_headers(('content-length', '{}'.format(len(COMPRESSED))))
    msg.send_headers()

    msg.enable_compression('deflate')
    msg.write(b'data')
    yield from msg.write_eof()

    chunks = [c[1][0] for c in list(write.mock_calls)]
    assert all(chunks)
    content = b''.join(chunks)
    assert COMPRESSED == content.split(b'\r\n\r\n', 1)[-1]


@asyncio.coroutine
def test_write_payload_deflate_and_chunked(transport):
    write = transport.write = mock.Mock()
    msg = protocol.Response(transport, 200)
    msg.send_headers()

    msg.enable_compression('deflate')
    msg.enable_chunking()

    msg.write(b'da')
    msg.write(b'ta')
    yield from msg.write_eof()

    chunks = [c[1][0] for c in list(write.mock_calls)]
    assert all(chunks)
    content = b''.join(chunks)
    print(content)
    assert (b'6\r\nKI,I\x04\x00\r\n0\r\n\r\n' ==
            content.split(b'\r\n\r\n', 1)[-1])


def test_write_drain(transport, loop):
    msg = protocol.Response(transport, 200, http_version=(1, 0), loop=loop)
    msg.drain = mock.Mock()
    msg.send_headers()
    msg.write(b'1' * (64 * 1024 * 2), drain=False)
    assert not msg.drain.called

    msg.write(b'1', drain=True)
    assert msg.drain.called
    assert msg.buffer_size == 0


def test_dont_override_request_headers_with_default_values(transport, loop):
    msg = protocol.Request(
        transport, 'GET', '/index.html', close=True, loop=loop)
    msg.add_header('USER-AGENT', 'custom')
    msg._add_default_headers()
    assert 'custom' == msg.headers['USER-AGENT']


def test_dont_override_response_headers_with_default_values(transport, loop):
    msg = protocol.Response(transport, 200, http_version=(1, 0), loop=loop)
    msg.add_header('DATE', 'now')
    msg.add_header('SERVER', 'custom')
    msg._add_default_headers()
    assert 'custom' == msg.headers['SERVER']
    assert 'now' == msg.headers['DATE']
