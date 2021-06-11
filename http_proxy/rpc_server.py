from http_proxy import rabbitmq, log
from http_proxy.models import Request, Response
from mitmproxy.net.http import http1
from mitmproxy.net.http.http1 import assemble
from mitmproxy.net.http.http1.read import read_response_head
from typing import Dict, Optional, Any
import base64
import json
import mitmproxy.net.http
import pika
import socket
import ssl

logger = log.getLogger("rpc_server", server=True)
TIMEOUT = 15

class RPCServer(object):
    """
    Base class for server instances. Please note that this class and this
    module are not multithreaded. Running multiple instances of this script as
    required is preferred as this avoids concurrency issues due to Python's GIL.
    """

    def get_raw_request(self, request : mitmproxy.net.http.Request) -> bytes:
        """
        Obtains the assembled raw bytes required for sending through a socket
        from a MITM Request object.

        Args:
            request: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html
        """
        request.decode(strict=False)
        raw_request : bytes = assemble.assemble_request(request) # type: ignore
        
        return raw_request

    def parse_response(self, request : mitmproxy.net.http.Request, 
            socket : socket.socket) -> mitmproxy.net.http.Response:
        """
        Instructs internal mitmproxy methods to parse the response from socket.
        
        Args:
            request: the original request. 
            socket: the socket to read from.
        Returns:
            response: the parsed response object with content populated.
        """
        response_file = socket.makefile(mode='rb')
        parsed_response : mitmproxy.net.http.Response = http1.read_response(response_file, request) # type: ignore

        return parsed_response

    def get_socket(self, request : mitmproxy.net.http.Request) -> socket.socket:
        """
        Gets the appropriate socket for the passed-in request. If SSL is
        required based on the request, a SSL wrapper is configured and returned
        instead.

        Several key security features are purposefully disabled in order to
        facilitate testing of hosts with broken SSL security. These features
        are hostname checking and TLS certificate verification. To add insult
        to injury, SSLv2 and SSLv3 are also enabled.

        Args:
            request: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html

        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)

        if request.scheme == "https":
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            context.options &= ~ssl.OP_NO_SSLv3
            context.options &= ~ssl.OP_NO_SSLv2

            ssl_sock = context.wrap_socket(sock, server_hostname=request.host)
            return ssl_sock
        else:
            return sock

    def send_request(self, request : mitmproxy.net.http.Request) -> mitmproxy.net.http.Response:
        """
        Main connection handler. Opens a socket, optionally wrapping with SSL
        if required and sends to destination.

        Args:
            request: the request as sent by the proxy. It will be assembled and
                sent.
        """
        sock = self.get_socket(request)
        sock.connect((request.host, request.port))

        request_bytes = self.get_raw_request(request)
        sock.send(request_bytes)

        response = self.parse_response(request, sock)

        return response

    def on_request(self, ch : pika.channel.Channel, method : Any, props :
            pika.spec.BasicProperties, body : bytes) -> None:
        """
        Callback endpoint called by pika. For more documentation on the arguments, please
        @see: https://pika.readthedocs.io/en/stable/modules/channel.html#pika.channel.Channel.basic_consume
        """

        if props.reply_to is None:
            logger.error("Received message without routing key. Ignoring. Body '%r'." % body)
            return

        try:
            request = Request.fromJSON(body).toMITM()
            logger.info("Successfully received message from queue. Sending to %s." % request.host)
        except json.decoder.JSONDecodeError:
            logger.exception("Couldn't decode a JSON object and am having a bad time. Body '%r'." % body)
            raise

        response = self.send_request(request)
        response_body = Response(response.get_state()).toJSON()

        my_props = pika.BasicProperties(correlation_id = props.correlation_id)
        ch.basic_publish(exchange='', routing_key=props.reply_to,
                         properties=my_props, body=response_body.encode('utf-8'))

def listen():
    started_once = False
    while True:
        try:
            connection = rabbitmq.new_connection()
            channel = connection.channel()
            channel.queue_declare(queue='rpc_queue')

            rpc_server = RPCServer()

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue='rpc_queue', on_message_callback=rpc_server.on_request, auto_ack=True)

            verb = "started" if started_once == False else "restarted"

            logger.info("HTTP Server consumer %s successfully. Listening for messages." % verb)
            started_once = True

            channel.start_consuming()

        except KeyboardInterrupt:
            logger.error("Received Ctrl + C. Shutting down...")
            break
        except:
            logger.exception("Unhandled exception in server thread. Will attempt to restart.", exc_info=True)
        finally:
            channel.stop_consuming()
            connection.close()

