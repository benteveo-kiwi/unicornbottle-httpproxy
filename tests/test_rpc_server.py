from tests.test_base import TestBase
from unittest.mock import MagicMock
from http_proxy.rpc_server import RPCServer
from http_proxy.rpc_client import Request
import pika

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

        host = "www.example.org"
        port = 80
        proto = "http"
        bytes = b"lalalala"

        req = Request(host, port, proto, bytes)

        return channel, method, props, req

    def test_on_request(self):
        server = self._getServer()
        ch, method, props, request = self._mocks()

        response_str = "response!"
        server.send_request = MagicMock(spec=RPCServer.send_request, return_value=response_str)

        server.on_request(ch, method, props, request.toJSON())

        self.assertEqual(server.send_request.call_count, 1)
        self.assertEqual(server.send_request.call_args.args[0].host, request.host)
        self.assertEqual(server.send_request.call_args.args[0].port, request.port)

        self.assertEqual(ch.basic_publish.call_count, 1)
        self.assertEqual(ch.basic_publish.call_args.kwargs['routing_key'], props.reply_to)
        self.assertEqual(ch.basic_publish.call_args.kwargs['properties'].correlation_id, props.correlation_id)
        self.assertEqual(ch.basic_publish.call_args.kwargs['body'], response_str)

