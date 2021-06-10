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

class TestRPCClient(TestBase):
    """
    This file contains tests related to rpc_client.py mostly.
    """

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
        req_state = self.EXAMPLE_REQ

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
        flow.request.get_state.return_value = self.EXAMPLE_REQ

        response = MagicMock()

        addon = HTTPProxyAddon()
        addon._request(client, flow)

        # Ensure can parse JSON
        rabbitRequest = json.loads(client.call.call_args.args[0])
        self.assertEqual(rabbitRequest['host'], flow.request.host)


if __name__ == '__main__':
    unittest.main()

