from rpc_client import HTTPProxyClient, TimeoutException
from unittest.mock import MagicMock
import pika
import unittest
import uuid

class TestHttpProxy(unittest.TestCase):

    def _mockConnection(self):
        return MagicMock(spec=pika.BlockingConnection)

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

if __name__ == '__main__':
    unittest.main()

