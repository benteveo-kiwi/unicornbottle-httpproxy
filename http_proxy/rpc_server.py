from http_proxy import rabbitmq, log
from http_proxy.models import Request
from typing import Dict, Optional, Any
import base64
import json
import pika
import socket

logger = log.getLogger("rpc_server", server=True)
TIMEOUT = 10

class RPCServer(object):
    """
    Base class for server instances. Please note that this class and this
    module are not multithreaded. Running multiple instances of this script as
    required is preferred as this avoids concurrency issues due to Python's GIL.
    """

    def send_request(self, request : Request) -> bytes:
        """
        Main connection handler. Opens a socket, optionally wrapping with SSL
        if required and sends to destination.

        Args:
            request: the request as sent by the proxy.
        """
        address = (request.host, request.port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        sock.settimeout(TIMEOUT)
        sock.connect(address)

        sock.send(base64.b64decode(request.encoded_bytes))

        raw_response = b""

        while True:
            try:
                msg = sock.recv(4096)
            except socket.timeout:
                logger.exception("Read timeout")
                raise
            except socket.error:
                logger.exception("Error reading from socket")
                raise
            else:
                print(msg)
                print("------------------------------------------------------------")
                print("------------------------------------------------------------")
                print("------------------------------------------------------------")
                print("------------------------------------------------------------")
                if len(msg) == 0:
                    break
                else:
                    raw_response += msg

        return raw_response

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
            request = Request.fromJSON(body)
            logger.info("Successfully received message from queue. Sending to %s." % request.host)
        except json.decoder.JSONDecodeError:
            logger.exception("Couldn't decode a JSON object and am having a bad time. Body '%r'." % body)
            raise

        response_body = self.send_request(request)

        my_props = pika.BasicProperties(correlation_id = props.correlation_id)
        ch.basic_publish(exchange='', routing_key=props.reply_to,
                         properties=my_props, body=response_body)

def listen():
    try:
        connection = rabbitmq.new_connection()
        channel = connection.channel()
        channel.queue_declare(queue='rpc_queue')

        rpc_server = RPCServer()

        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue='rpc_queue', on_message_callback=rpc_server.on_request, auto_ack=True)

        logger.info("[+] HTTP Server consumer started successfully. Listening for messages.")
        channel.start_consuming()
    except:
        logger.exception("Unhandled exception in server init thread.", exc_info=True)
    finally:
        connection.close()

