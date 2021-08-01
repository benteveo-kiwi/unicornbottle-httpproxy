from http_proxy.models import Response, Request
from http_proxy.rpc_client import HTTPProxyClient, HTTPProxyAddon
from http_proxy.rpc_client import TimeoutException
from http_proxy.rpc_server import RPCServer
from unicornbottle.models import DatabaseWriteItem
from unittest.mock import MagicMock
import mitmproxy
import pika
import unittest

class TestBase(unittest.TestCase):
    HTTP_RESP = b"""HTTP/1.1 200 OK
Date: Mon, 27 Jul 2009 12:28:53 GMT
Server: Apache/2.2.14 (Win32)
Last-Modified: Wed, 22 Jul 2009 19:15:56 GMT
Content-Length: 2
Content-Type: text/html
Connection: Closed

OK"""

    TEST_GUID = b"3935729b-c1f7-40ab-9dfc-e19b699c2eae"

    EXAMPLE_REQ = {
        "http_version": b"HTTP/1.1",
        "headers": (
            (b"User-Agent", b"Wget/1.21"),
            (b"Accept", b"*/*"),
            (b"Accept-Encoding", b"identity"),
            (b"Host", b"www.testing.local"),
            (b"Connection", b"Keep-Alive"),
            (b"Proxy-Connection", b"Keep-Alive"),
            (b"X-UB-GUID", TEST_GUID),
        ),
        "content": b"",
        "trailers": None,
        "timestamp_start": 1623276395.5825248,
        "timestamp_end": 1623276395.5842779,
        "host": "www.testing.local",
        "port": 80,
        "method": b"GET",
        "scheme": b"http",
        "authority": b"",
        "path": b"/testpath",
    }

    EXAMPLE_RESP = {
		"http_version": b"HTTP/1.1",
		"headers": (
			(b"Content-Type", b"text/html; charset=UTF-8"),
			(b"Referrer-Policy", b"no-referrer"),
			(b"Content-Length", b"1563"),
			(b"Date", b"Thu, 10 Jun 2021 01:59:56 GMT"),
		),
		"content": b'<!DOCTYPE html>\n<html lang=en>\n  <meta charset=utf-8>\n  <meta name=viewport content="initial-scale=1, minimum-scale=1, width=device-width">\n  <title>Error 404 (Not Found)!!1</title>\n  <style>\n    *{margin:0;padding:0}html,code{font:15px/22px arial,sans-serif}html{background:#fff;color:#222;padding:15px}body{margin:7% auto 0;max-width:390px;min-height:180px;padding:30px 0 15px}* > body{background:url(//www.google.com/images/errors/robot.png) 100% 5px no-repeat;padding-right:205px}p{margin:11px 0 22px;overflow:hidden}ins{color:#777;text-decoration:none}a img{border:0}@media screen and (max-width:772px){body{background:none;margin-top:0;max-width:none;padding-right:0}}#logo{background:url(//www.google.com/images/branding/googlelogo/1x/googlelogo_color_150x54dp.png) no-repeat;margin-left:-5px}@media only screen and (min-resolution:192dpi){#logo{background:url(//www.google.com/images/branding/googlelogo/2x/googlelogo_color_150x54dp.png) no-repeat 0% 0%/100% 100%;-moz-border-image:url(//www.google.com/images/branding/googlelogo/2x/googlelogo_color_150x54dp.png) 0}}@media only screen and (-webkit-min-device-pixel-ratio:2){#logo{background:url(//www.google.com/images/branding/googlelogo/2x/googlelogo_color_150x54dp.png) no-repeat;-webkit-background-size:100% 100%}}#logo{display:inline-block;height:54px;width:150px}\n  </style>\n  <a href=//www.google.com/><span id=logo aria-label=Google></span></a>\n  <p><b>404.</b> <ins>That\xe2\x80\x99s an error.</ins>\n  <p>The requested URL <code>/aa</code> was not found on this server.  <ins>That\xe2\x80\x99s all we know.</ins>\n',
		"trailers": None,
		"timestamp_start": 1623290396.0925732,
		"timestamp_end": 1623290396.127658,
		"status_code": 404,
		"reason": b"Not Found",
	}


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
        req = Request(self.EXAMPLE_REQ.copy())

        return req

    def _resp(self):
        resp = Response(self.EXAMPLE_RESP.copy())

        return resp

    def _mockConnection(self):
        return MagicMock(spec=pika.BlockingConnection)

    def _mockChannel(self):
        return MagicMock(spec=pika.channel.Channel)

    def _mockQueue(self):
        return MagicMock()

    def _mockHTTPClient(self):
        return MagicMock(spec=HTTPProxyClient)

    def _mockFlow(self):
        flow = MagicMock(spec=mitmproxy.http.HTTPFlow)
        flow.request = MagicMock()

        flow.request.host = "www.testing.local"
        flow.request.port = 80
        flow.request.scheme = "http"
        
        return flow

    def _hpcWithMockedConn(self):
        hpc = HTTPProxyClient()
        hpc.rabbit_connection = self._mockConnection()
        hpc.channel = self._mockChannel()
        hpc.callback_queue = self._mockQueue()

        hpc.threads_alive = MagicMock(return_value=True)

        return hpc

    def _dwi(self):
        dwi = DatabaseWriteItem(self.TEST_GUID, self._req().toMITM(),
                self._resp().toMITM(), None)

        return dwi

