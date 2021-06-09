from http_proxy.rpc_client import HTTPProxyClient, Request, HTTPProxyAddon
from http_proxy.rpc_client import TimeoutException, AlreadyCalledException
from unittest.mock import MagicMock
from tests.test_base import TestBase
import mitmproxy
import base64
import json
import pika
import unittest
import uuid

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
        (b"Host", b"google.com"),
        (b"Connection", b"Keep-Alive"),
        (b"Proxy-Connection", b"Keep-Alive"),
    ),
    "content": b"",
    "trailers": None,
    "timestamp_start": 1623276395.5825248,
    "timestamp_end": 1623276395.5842779,
    "host": "google.com",
    "port": 80,
    "method": b"GET",
    "scheme": b"http",
    "authority": b"",
    "path": b"/",
}

class TestRPCClient(TestBase):
    """
    This file contains tests related to rpc_client.py mostly.
    """

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

    def test_constructor(self):
        conn = self._mockConnection()
        hpc = HTTPProxyClient(conn)
        
        self.assertEqual(hpc.response, None)
        self.assertEqual(hpc.channel, conn.channel())
        self.assertEqual(hpc.callback_queue, conn.channel().queue_declare().method.queue)

    def test_on_response(self):
        conn = self._mockConnection()
        hpc = HTTPProxyClient(conn)

        class MockProp():
            def __init__(self, correlation_id):
                self.correlation_id = correlation_id

        nb_response = 1337

        hpc.corr_id = str(uuid.uuid4())
        hpc.on_response(None, None, MockProp(hpc.corr_id), nb_response)

        self.assertEqual(hpc.response, nb_response)

    def test_call(self):
        conn = self._mockConnection()
        hpc = HTTPProxyClient(conn)

        def _side_effect(*args, **kwargs):
            hpc.response = 1337

        hpc.connection.process_data_events.side_effect = _side_effect

        param = "param"

        ret = hpc.call(param)

        self.assertEqual(hpc.channel.basic_publish.call_args.kwargs['body'], param)
        self.assertEqual(ret, 1337)

    def test_call_timeout(self):
        conn = self._mockConnection()
        hpc = HTTPProxyClient(conn)

        def _side_effect(*args, **kwargs):
            hpc.response = None

        hpc.connection.process_data_events.side_effect = _side_effect

        with self.assertRaises(TimeoutException):
            ret = hpc.call("param")


    def test_call_can_only_call_once(self):
        conn = self._mockConnection()
        hpc = HTTPProxyClient(conn)

        def _side_effect(*args, **kwargs):
            hpc.response = 1337

        hpc.connection.process_data_events.side_effect = _side_effect

        param = "param"

        ret = hpc.call(param)
        with self.assertRaises(AlreadyCalledException):
            ret = hpc.call(param)
    
    def test_request_encoder(self):
        req_state = EXAMPLE_REQ

        req = Request(req_state)

        j = req.toJSON()

        req_parsed = Request.fromJSON(j)

        self.assertEqual(req_state['host'], req_parsed.request_state['host'])
        self.assertEqual(req_state['port'], req_parsed.request_state['port'])
        self.assertEqual(req_state['method'], req_parsed.request_state['method'])
        self.assertEqual(req_state['scheme'], req_parsed.request_state['scheme'])
        self.assertEqual(req_state['path'], req_parsed.request_state['path'])

        self.assertEqual(len(req_state['headers']), len(req_parsed.request_state['headers']))

    def test_request_method(self):
        client = self._mockHTTPClient()
        flow = self._mockFlow()
        raw_request = b"raw_request"

        response = MagicMock()

        addon = HTTPProxyAddon()
        addon.get_raw_request = MagicMock(return_value=raw_request)
        addon.parse_response = MagicMock(return_value=response)

        addon._request(client, flow)

        # Ensure can parse JSON
        rabbitRequest = json.loads(client.call.call_args.args[0])
        self.assertEqual(rabbitRequest['host'], flow.request.host)

        # Ensure response is replaced in flow.
        self.assertEqual(flow.response, response)

    def test_parse_response(self):
        addon = HTTPProxyAddon()
        flow = self._mockFlow()

        resp = addon.parse_response(flow.request, HTTP_RESP)

        self.assertEqual(resp.content, b"OK")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-length"], "2")

if __name__ == '__main__':
    unittest.main()

