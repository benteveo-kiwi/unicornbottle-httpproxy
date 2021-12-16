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
        server = self._getServer()
        server.get_socket = MagicMock(spec=RPCServer.get_socket, return_value=socket.return_value)
        server.parse_response = MagicMock(spec=RPCServer.parse_response)
        server.get_raw_request = MagicMock(spec=RPCServer.get_raw_request)
        req = self._req().toMITM()

        resp = server.send_request(req)

        sock_instance = socket.return_value

        self.assertEqual(sock_instance.connect.call_count, 1)
        self.assertEqual(sock_instance.connect.call_args[0][0], ('www.testing.local', 80))

        self.assertEqual(sock_instance.send.call_count, 1)
        self.assertEqual(sock_instance.send.call_args[0][0], server.get_raw_request.return_value)

        self.assertEqual(resp, server.parse_response.return_value)

    @patch("ssl.create_default_context", autospec=True)
    @patch("socket.socket", autospec=True)
    def test_get_socket(self, socket, ssl_cdc):

        server = self._getServer()

        req = self._req()
        returned_socket = server.get_socket(req.toMITM())

        self.assertEqual(socket.return_value, returned_socket) # scheme == http on default test request.
        self.assertEqual(socket.return_value.settimeout.call_count, 1) # need to timeout sometime.
        
        req = self._req()
        req.state['scheme'] = 'https'
        returned_socket = server.get_socket(req.toMITM())

        self.assertEqual(ssl_cdc().wrap_socket(), returned_socket) # scheme == http on default test request.

    def test_colon_in_host(self):
        assert False

