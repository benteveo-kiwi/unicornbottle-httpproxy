from http_proxy.rpc_client import HTTPProxyClient, Request, HTTPProxyAddon
from http_proxy.rpc_client import TimeoutException
from tests.test_base import TestBase
from unittest.mock import MagicMock, patch
import base64
import json
import mitmproxy
import pika
import time
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
        hpc = HTTPProxyClient()

        class MockProp():
            def __init__(self, correlation_id):
                self.correlation_id = correlation_id

        nb_response = 1337

        corr_id = str(uuid.uuid4())
        hpc.corr_ids[corr_id] = True
        hpc.on_response(None, None, MockProp(corr_id), nb_response)

        self.assertEqual(hpc.responses[corr_id], nb_response)

    @patch("http_proxy.rpc_client.partial", autospec=True)
    def test_call(self, ftp):
        hpc = HTTPProxyClient()
        hpc.connection = self._mockConnection()
        hpc.channel = self._mockChannel()
        hpc.callback_queue = self._mockQueue()
        
        corr_id = uuid.uuid4()
        body = "param"

        hpc.responses[corr_id] = 1337

        ret = hpc.call(body, corr_id)

        args, kwargs = ftp.call_args

        self.assertEqual(hpc.connection.add_callback_threadsafe.call_count, 1)
        self.assertEqual(args[0], hpc.channel.basic_publish)
        self.assertEqual(kwargs['body'], body)
        self.assertEqual(kwargs['properties'].correlation_id, corr_id)
        self.assertEqual(kwargs['properties'].reply_to, hpc.callback_queue)

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

        self.assertEqual(req_state['host'], req_parsed.state['host'])
        self.assertEqual(req_state['port'], req_parsed.state['port'])
        self.assertEqual(req_state['method'], req_parsed.state['method'])
        self.assertEqual(req_state['scheme'], req_parsed.state['scheme'])
        self.assertEqual(req_state['path'], req_parsed.state['path'])

        self.assertEqual(len(req_state['headers']), len(req_parsed.state['headers']))

    def test_request_method(self):
        response = self._resp()
        client = self._mockHTTPClient()
        client.call.return_value = response.toJSON()

        flow = self._mockFlow()
        flow.request.get_state.return_value = self.EXAMPLE_REQ

        addon = HTTPProxyAddon(client)
        addon._request(client, flow, time.time(), uuid.uuid4())

        # Ensure can parse JSON
        rabbitRequest = json.loads(client.call.call_args.args[0])
        self.assertEqual(rabbitRequest['host'], flow.request.host)

        # Check responses are replaced.
        self.assertEqual(flow.response.http_version, response.state['http_version'].decode('utf-8'))
        self.assertEqual(len(flow.response.headers), len(response.state['headers']))
        self.assertEqual(flow.response.content, response.state['content'])

if __name__ == '__main__':
    unittest.main()

