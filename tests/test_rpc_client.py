from http_proxy.rpc_client import HTTPProxyAddon
from sqlalchemy import exc
from tests.test_base import TestBase
from unicornbottle.models import DatabaseWriteItem, RequestResponse
from unicornbottle.models import Request
from unicornbottle.proxy import HTTPProxyClient, TimeoutException, UnauthorizedException
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

    @patch("unicornbottle.proxy.partial", autospec=True)
    def test_call(self, ftp):
        hpc = self._hpcWithMockedConn() 

        corr_id = uuid.uuid4()
        body = self._req().toMITM()

        resp = self._resp()
        resp.state['status_code'] = 309
        hpc.responses[corr_id] = resp.toJSON()

        ret = hpc.send_request(body, corr_id)

        args, kwargs = ftp.call_args

        self.assertEqual(hpc.rabbit_connection.add_callback_threadsafe.call_count, 1)
        self.assertEqual(args[0], hpc.channel.basic_publish)
        self.assertEqual(kwargs['body'], self._req().toJSON())
        self.assertEqual(kwargs['properties'].correlation_id, corr_id)
        self.assertEqual(kwargs['properties'].reply_to, hpc.callback_queue)

        self.assertEqual(ret.status_code, 309) # made up status to ensure the response is the same.

    def test_call_timeout(self):
        hpc = self._hpcWithMockedConn()
        hpc.PROCESS_TIME_LIMIT = 0.00001

        with self.assertRaises(TimeoutException):
            ret = hpc.send_request(self._req().toMITM(), "corr_id")

    def test_call_can_call_multiple_times(self):
        hpc = self._hpcWithMockedConn() 

        corr_id1 = uuid.uuid4()
        corr_id2 = uuid.uuid4()
        body = self._req().toMITM()

        resp1 = self._resp().toJSON()

        resp2 = self._resp()
        resp2.state['status_code'] = 200
        resp2 = resp2.toJSON()

        hpc.responses[corr_id1] = resp1
        hpc.responses[corr_id2] = resp2

        ret1 = hpc.send_request(body, corr_id1)
        ret2 = hpc.send_request(body, corr_id2)

        self.assertEqual(ret1.status_code, 404)
        self.assertEqual(ret2.status_code, 200)

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
        client.send_request.return_value = response.toMITM()

        flow = self._mockFlow()
        flow.request.get_state.return_value = self.EXAMPLE_REQ

        addon = HTTPProxyAddon(client)
        addon._request(flow)

        # Ensure can parse JSON
        sent_request = client.send_request.call_args.args[0]
        self.assertEqual(sent_request.host, flow.request.host)

        # Check responses are replaced.
        self.assertEqual(flow.response.http_version, response.state['http_version'].decode('utf-8'))
        self.assertEqual(len(flow.response.headers), len(response.state['headers']))
        self.assertEqual(flow.response.content, response.state['content'])

    def test_queue_write_success(self):
        hpc = self._hpcWithMockedConn() 
        hpc.db_write_queue = MagicMock()
        hpc.get_response = MagicMock()

        corr_id = uuid.uuid4()
        body = self._req().toMITM()
        hpc.responses[corr_id] = self._resp().toJSON()
        ret = hpc.send_request(body, corr_id)

        self.assertEqual(hpc.db_write_queue.put.call_count, 1)

        dwi = hpc.db_write_queue.put.call_args[0][0]
        self.assertEqual(dwi.exception, None)
        self.assertEqual(dwi.response, hpc.get_response.return_value)

    def test_queue_no_write_if_no_target(self):
        hpc = self._hpcWithMockedConn() 
        hpc.db_write_queue = MagicMock()

        corr_id = uuid.uuid4()
        req = self._req()
        req.state['headers'] = (
            (b"User-Agent", b"Wget/1.21"),
            (b"Host", b"www.testing.local"),
        )

        body = req.toMITM()
        hpc.responses[corr_id] = self._resp().toJSON()
        with self.assertRaises(UnauthorizedException):
            hpc.send_request(body, corr_id)

        self.assertEqual(hpc.db_write_queue.put.call_count, 0)

    def test_queue_no_write_if_malformed(self):
        hpc = self._hpcWithMockedConn() 
        hpc.db_write_queue = MagicMock()

        corr_id = uuid.uuid4()
        req = self._req()
        req.state['headers'] = (
            (b"User-Agent", b"Wget/1.21"),
            (b"Host", b"www.testing.local"),
            (b"X-UB-GUID", b"Is this a valid GUID? I shouldn't think so!"),
        )

        body = req.toMITM()
        hpc.responses[corr_id] = self._resp().toJSON()
        with self.assertRaises(UnauthorizedException):
            hpc.send_request(body, corr_id)

        self.assertEqual(hpc.db_write_queue.put.call_count, 0)

    def test_queue_write_timeout(self):
        hpc = self._hpcWithMockedConn() 
        hpc.db_write_queue = MagicMock()
        exc_message = "Message"
        exc = TimeoutException(exc_message)
        hpc.get_response = MagicMock(side_effect=exc)

        corr_id = uuid.uuid4()
        body = self._req().toMITM()
        hpc.responses[corr_id] = self._resp().toJSON()

        with self.assertRaises(TimeoutException):
            ret = hpc.send_request(body, corr_id)

        # Should still write even if there has been an exception
        self.assertEqual(hpc.db_write_queue.put.call_count, 1)

        dwi = hpc.db_write_queue.put.call_args[0][0]
        self.assertEqual(dwi.exception.state['type'], "TimeoutException")
        self.assertEqual(dwi.exception.state['value'], exc_message)
        self.assertEqual(dwi.response, None)

    def test_queue_write_otherexception(self):
        hpc = self._hpcWithMockedConn() 
        hpc.db_write_queue = MagicMock()
        hpc.rabbit_connection = MagicMock()

        class WhateverException(Exception):
            pass

        exc = WhateverException("Oops.")
        hpc.rabbit_connection.add_callback_threadsafe.side_effect = exc

        corr_id = uuid.uuid4()
        body = self._req().toMITM()
        hpc.responses[corr_id] = self._resp().toJSON()

        with self.assertRaises(WhateverException):
            ret = hpc.send_request(body, corr_id)

        # Should still write even if there has been an exception
        self.assertEqual(hpc.db_write_queue.put.call_count, 1)

        dwi = hpc.db_write_queue.put.call_args[0][0]
        self.assertEqual(dwi.exception.state['type'], "WhateverException")
        self.assertEqual(dwi.exception.state['value'], "Oops.")
        self.assertEqual(dwi.response, None)

    def test_queue_read_empty_queue(self):
        hpc = self._hpcWithMockedConn() 
        hpc.thread_postgres_write = MagicMock(spec=HTTPProxyClient.thread_postgres_write)
        hpc.thread_postgres_read_queue()

        self.assertEqual(hpc.thread_postgres_write.call_count, 0)

    def test_queue_read(self):
        hpc = self._hpcWithMockedConn() 
        hpc.thread_postgres_write = MagicMock(spec=HTTPProxyClient.thread_postgres_write)

        dwi = self._dwi()
        hpc.db_write_queue.put(dwi)

        hpc.thread_postgres_read_queue()
        self.assertEqual(hpc.thread_postgres_write.call_count, 1)

        req_resp = hpc.thread_postgres_write.call_args.args[0][self.TEST_GUID][0]

        self.assertEqual(type(req_resp), RequestResponse)
        self.assertEqual(req_resp.method, "GET")
        self.assertEqual(req_resp.path, "/testpath")

    def test_queue_read_10(self):
        hpc = self._hpcWithMockedConn() 
        hpc.thread_postgres_write = MagicMock(spec=HTTPProxyClient.thread_postgres_write)

        dwi = self._dwi()
        for _ in range(10):
            hpc.db_write_queue.put(dwi)

        hpc.thread_postgres_read_queue()
        self.assertEqual(hpc.thread_postgres_write.call_count, 1)
        self.assertEqual(len(hpc.thread_postgres_write.call_args.args[0][dwi.target_guid]), 10)
    
    def test_queue_read_100(self):
        hpc = self._hpcWithMockedConn() 
        hpc.thread_postgres_write = MagicMock(spec=HTTPProxyClient.thread_postgres_write)

        dwi = self._dwi()
        for _ in range(100):
            hpc.db_write_queue.put(dwi)

        hpc.thread_postgres_read_queue()
        self.assertEqual(hpc.thread_postgres_write.call_count, 1)
        self.assertEqual(len(hpc.thread_postgres_write.call_args.args[0][dwi.target_guid]), 100)

    def test_queue_read_105(self):
        hpc = self._hpcWithMockedConn() 
        hpc.thread_postgres_write = MagicMock(spec=HTTPProxyClient.thread_postgres_write)

        dwi = self._dwi()
        for _ in range(105):
            hpc.db_write_queue.put(dwi)

        hpc.thread_postgres_read_queue()
        self.assertEqual(hpc.thread_postgres_write.call_count, 1)
        self.assertEqual(len(hpc.thread_postgres_write.call_args.args[0][dwi.target_guid]), 100)

        hpc.thread_postgres_read_queue()
        self.assertEqual(len(hpc.thread_postgres_write.call_args.args[0][dwi.target_guid]), 5)

    def test_db_write(self):
        hpc = self._hpcWithMockedConn() 

        write = {self.TEST_GUID: [RequestResponse.createFromDWI(self._dwi())]}

        with patch('unicornbottle.proxy.database_connect') as dc:
            hpc.thread_postgres_write(write)

            self.assertEqual(dc.call_count, 1)
            self.assertEqual(dc.return_value.add.call_count, 1)

            req_resp = dc.return_value.add.call_args.args[0]
            self.assertEqual(req_resp.metadata_id, dc().execute().scalar.return_value.id)

            self.assertEqual(type(req_resp), RequestResponse)
            self.assertEqual(req_resp.method, "GET")
            self.assertEqual(req_resp.path, "/testpath")
    
    def test_queue_read_handle_write_exception(self):
        hpc = self._hpcWithMockedConn() 
        hpc.thread_postgres_write = MagicMock(spec=HTTPProxyClient.thread_postgres_write, side_effect=exc.SQLAlchemyError)

        dwi = self._dwi()
        for _ in range(105):
            hpc.db_write_queue.put(dwi)

        hpc.thread_postgres_read_queue()
        self.assertEqual(hpc.thread_postgres_write.call_count, 1)

if __name__ == '__main__':
    unittest.main()

