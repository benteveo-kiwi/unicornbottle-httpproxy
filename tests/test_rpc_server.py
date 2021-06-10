from tests.test_base import TestBase
from unittest.mock import MagicMock, patch
from http_proxy.rpc_server import RPCServer
from http_proxy.rpc_client import Request
import pika
import base64

class TestRPCServer(TestBase):
    """
    This file contains tests related to rpc_client.py mostly.
    """

    def _getServer(self):
        rpc_server = RPCServer()

        return rpc_server

    def _mocks(self):
        channel = MagicMock(spec=pika.channel.Channel)
        method = MagicMock()
        props = MagicMock(spec=pika.spec.BasicProperties)
        props.reply_to = "347269b8-0fff-4622-acd7-e4382f3f22ed"
        props.correlation_id = "999269b8-0fff-4622-acd7-e4382f3f22ed"

        req = self._req()

        return channel, method, props, req

    def _req(self):
        req = Request(self.EXAMPLE_REQ)

        return req

    def test_on_request(self):
        server = self._getServer()
        ch, method, props, request = self._mocks()

        response_str = "response!"
        server.send_request = MagicMock(spec=RPCServer.send_request, return_value=response_str)

        server.on_request(ch, method, props, request.toJSON())

        self.assertEqual(server.send_request.call_count, 1)
        self.assertTrue(False)

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
        

