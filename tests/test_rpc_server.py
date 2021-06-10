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
        req = Request(self.EXAMPLE_REQ)

        return req

    def test_on_request(self):
        server = self._getServer()
        ch, method, props, request = self._mocks()

        resp_mock = Response(self.EXAMPLE_RESP).toMITM()
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

