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
        hpc = self._hpcWithMockedConn() 

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
        hpc = self._hpcWithMockedConn()
        hpc.PROCESS_TIME_LIMIT = 0.00001

        with self.assertRaises(TimeoutException):
            ret = hpc.call("param", "corr_id")

    def test_call_can_call_multiple_times(self):
        hpc = self._hpcWithMockedConn() 

        corr_id1 = uuid.uuid4()
        corr_id2 = uuid.uuid4()
        body = "param"

        hpc.responses[corr_id1] = 1337
        hpc.responses[corr_id2] = 1338

        ret1 = hpc.call(body, corr_id1)
        ret2 = hpc.call(body, corr_id2)

        self.assertEqual(ret1, 1337)
        self.assertEqual(ret2, 1338)

        self.assertEqual(len(hpc.responses), 0)
    
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

