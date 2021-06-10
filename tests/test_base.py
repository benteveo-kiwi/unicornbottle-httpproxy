import unittest
from http_proxy.rpc_client import HTTPProxyClient, Request, HTTPProxyAddon
from http_proxy.rpc_client import TimeoutException, AlreadyCalledException
import mitmproxy
import pika
from unittest.mock import MagicMock

class TestBase(unittest.TestCase):
    HTTP_RESP = b"""HTTP/1.1 200 OK
Date: Mon, 27 Jul 2009 12:28:53 GMT
Server: Apache/2.2.14 (Win32)
Last-Modified: Wed, 22 Jul 2009 19:15:56 GMT
Content-Length: 2
Content-Type: text/html
Connection: Closed

OK"""

    EXAMPLE_REQ = {
        "http_version": b"HTTP/1.1",
        "headers": (
            (b"User-Agent", b"Wget/1.21"),
            (b"Accept", b"*/*"),
            (b"Accept-Encoding", b"identity"),
            (b"Host", b"www.testing.local"),
            (b"Connection", b"Keep-Alive"),
            (b"Proxy-Connection", b"Keep-Alive"),
        ),
        "content": b"",
        "trailers": None,
        "timestamp_start": 1623276395.5825248,
        "timestamp_end": 1623276395.5842779,
        "host": "www.testing.local",
        "port": 80,
        "method": b"GET",
        "scheme": b"http",
        "authority": b"",
        "path": b"/",
    }

    def _mockConnection(self):
        return MagicMock(spec=pika.BlockingConnection)

    def _mockHTTPClient(self):
        return MagicMock(spec=HTTPProxyClient)

    def _mockFlow(self):
        flow = MagicMock(spec=mitmproxy.http.HTTPFlow)
        flow.request = MagicMock()

        flow.request.host = "www.testing.local"
        flow.request.port = 80
        flow.request.scheme = "http"
        
        return flow
