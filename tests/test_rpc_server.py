from http_proxy.rpc_server import RPCServer
from http_proxy.models import Response, Request
from tests.test_base import TestBase
from io import BytesIO
from unittest.mock import MagicMock, patch
import base64
import pika
import json

class TestRPCServer(TestBase):
    """
    This file contains tests related to rpc_client.py mostly.
    """

    def test_on_request(self):
        server = self._getServer()
        ch, method, props, request = self._mocks()

        resp_mock = self._resp().toMITM()
        server.send_request = MagicMock(spec=RPCServer.send_request,
                return_value=resp_mock)

        server.on_request(ch, method, props, request.toJSON())

        self.assertEqual(server.send_request.call_count, 1)
        self.assertEqual(ch.basic_publish.call_count, 1)
        
        parsed_body = json.loads(ch.basic_publish.call_args.kwargs['body'])

        self.assertEqual(parsed_body['status_code'], 404)

    def test_parse_response(self):
        server = self._getServer()
        flow = self._mockFlow()

        fakeSocket = MagicMock()
        fakeSocket.makefile.return_value = BytesIO(self.HTTP_RESP)

        resp = server.parse_response(flow.request, fakeSocket)

        self.assertEqual(resp.content, b"OK")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-length"], "2")

    @patch("socket.socket", autospec=True)
    def test_send_request(self, socket):
        self.assertTrue(False)
        server = self._getServer()
        req = self._req()

        i = 0
        def func(*args, **kwargs):
            if i == 0:
                i += 1
                return "WhateverResponse"

        socket.send.return_value = func

        server.send_request(req)

        self.assertEquals(socket.call_count, 1)

    def test_send_request_ssl(self):
        self.assertTrue(False)

