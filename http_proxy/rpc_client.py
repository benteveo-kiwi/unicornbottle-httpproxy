from http_proxy import rabbitmq, log
from http_proxy.models import Request, Response
from io import BytesIO
from mitmproxy.script import concurrent
from threading import Event, Thread
from typing import Dict, Optional, Any
import base64
import functools
import logging
import mitmproxy
import pika
import sys
import threading
import time
import uuid

# https://www.postgresql.org/docs/8.3/wal-async-commit.html

PROCESS_TIME_LIMIT = 15
logger = logging.getLogger(__name__)

class TimeoutException(Exception):
    pass

class NotConnectedException(Exception):
    pass

class HTTPProxyClient(object):
    """
    This function implements the RPC model in a thread-safe way.
    """

    def __init__(self) -> None:
        """
        Connect to RabbitMQ. Creating a new connection per thread is OK per Pika's author 
        @see: https://github.com/pika/pika/issues/828#issuecomment-357773396
        Args:
            connection: a BlockingConnection instance.
        """

        self.lock = threading.Lock()

        self.connection : Optional[pika.BlockingConnection] = None
        self.channel : Optional[pika.channel.Channel] = None


        self.corr_ids : Dict[str, bool] = {}
        self.responses : Dict[str, bytes] = {}

        self.thread = self.spawn_thread()

    def spawn_thread(self) -> threading.Thread:
        """
        Creates an instance of the connection thread.

        Return:
            threading.Thread
        """
        thread = threading.Thread(target=self.init_connection)
        thread.start()
        return thread

    def init_connection(self):
        """
        Initializes the responses queue and handles consumption of responses.
        This is a blocking function and should be called from another thread.
        """
        try:
            self.connection = rabbitmq.new_connection()
            self.channel = self.connection.channel()

            # Create a queue for handling the responses.
            result = self.channel.queue_declare(queue='', exclusive=True)
            self.callback_queue = result.method.queue
            self.channel.basic_consume(
                queue=self.callback_queue,
                on_message_callback=self.on_response,
                auto_ack=True)

            logger.info("Thread ready to start consuming")
            self.channel.start_consuming() 
        except:
            logger.exception("Exception in consumer thread")
        finally:
            logger.error("Consumer thread is shutting down. See log for details.")
            if self.connection:
                self.connection.close()

    def on_response(self, ch : Any, method : Any, props : pika.spec.BasicProperties, body : bytes) -> None:
        """
        Gets called when a response is issued as per the RPC pattern.

        Args: 
            see https://pika.readthedocs.io/en/stable/modules/channel.html#pika.channel.Channel.basic_consume

        See:
            https://www.rabbitmq.com/tutorials/tutorial-six-python.html
        """
        with self.lock:
            if props.correlation_id is None:
                logger.error("Received message without correlation id?")
                return

            if props.correlation_id in self.corr_ids:
                self.responses[props.correlation_id] = body
                del self.corr_ids[props.correlation_id]

    def call(self, message_body : bytes, corr_id : str) -> bytes:
        """
        THIS FUNCTION IS CALLED BY MULTIPLE THREADS. Special care is needed in
        order to comply with pika's threading model. In short:

        - Calls to connection or channel objects need to be done using the
          add_callback_threadsafe function. 
        - More information here:
            https://github.com/pika/pika/blob/0.13.1/examples/basic_consumer_threaded.py
            https://stackoverflow.com/questions/55373867/how-to-add-multiprocessing-to-consumer-with-pika-rabbitmq-in-python
            https://stackoverflow.com/questions/65516220/what-is-the-use-of-add-callback-threadsafe-method-in-pika

        Handles writing to queue, polling until a response is received and timeouts.

        Args:
            message_body: A JSON serialised `Request` Object.
            corr_id: the correlation id for this request, a uuid.

        Raises:
            TimeoutException: PROCESS_TIME_LIMIT exceeded, request timeout.
        """

        if self.channel is None or self.connection is None:
            if not self.thread.is_alive():
                self.thread = self.spawn_thread()

            raise NotConnectedException("Not connected?") # still raise. Clients must retry.

        self.corr_ids[corr_id] = True

        basic_pub = functools.partial(self.channel.basic_publish, exchange='', routing_key='rpc_queue',
            properties=pika.BasicProperties(reply_to=self.callback_queue, correlation_id=corr_id,),
            body=message_body)

        self.connection.add_callback_threadsafe(basic_pub)

        start = time.time()
        try:
            while True:
                resp = None
                try:
                    resp = self.responses[corr_id]
                except KeyError:
                    pass

                timeout = time.time() - start >= PROCESS_TIME_LIMIT

                if not resp and timeout:
                    raise TimeoutException
                elif resp:
                    return self.responses[corr_id]

                time.sleep(0.01) # sleep outside of the lock.

        finally:
            with self.lock:
                try:
                    del self.corr_ids[corr_id]
                except KeyError:
                    pass

                try:
                    del self.responses[corr_id]
                except KeyError:
                    pass


class HTTPProxyAddon(object):
    """
    Handles integration with mitmproxy.
    """

    def __init__(self):
        logger.info("Mitmproxy addon started.")

        http_proxy_client = HTTPProxyClient()

        self.client : HTTPProxyClient = http_proxy_client

        logger.info("Established connection to RabbitMQ.")

    def done(self):
        """
        Called when mitmproxy exits.
        """
        logger.info("Exiting cleanly. Attempting to stop consuming queues.")
        self.client.connection.add_callback_threadsafe(self.client.channel.stop_consuming)
        logger.info("Exited.")

    @concurrent # type: ignore
    def request(self, flow: mitmproxy.http.HTTPFlow) -> None:
        """
        Main mitmproxy entry point. This function gets called on each request
        received after mitmproxy handles all the underlying HTTP shenanigans.

        For more documentation, you can run the following command:

        pydoc3 mitmproxy.http
        pydoc3 mitmproxy.net.http.request
        """
        try:
            time_start = time.time()
            corr_id = str(uuid.uuid4())
            logger.debug("%s:Started handling for url %s" % (corr_id, flow.request.pretty_url))

            self._request(self.client, flow, time_start, corr_id)
            time_handled = time.time() - time_start

            logger.debug("%s:Done handling request in %s seconds" % (corr_id, time.time() - time_start))

        except:
            logger.exception("Unhandled exception in request thread.", exc_info=True)
            flow.response = mitmproxy.http.HTTPResponse.make(502, b"HTTP Proxy unhandled exception")

    def _request(self, http_proxy_client : HTTPProxyClient, flow : mitmproxy.http.HTTPFlow, time_start:float, corr_id:str) -> None:
        """
        Internal method to facilitate dependency injection for testing.

        Args:
            http_proxy_client: Instance of HTTPProxyClient.
            flow: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html
            time_start: float indicating the time.time() at the time we started processing this request.
            corr_id: the correlation_id for this request.
        """

        req = Request(flow.request.get_state())
        logger.debug("%s:Finished parsing request." % (corr_id))
        response_json = http_proxy_client.call(req.toJSON().encode('utf-8'), corr_id)
        logger.debug("%s:Finished receiving response, parsing. Took %s seconds." % (corr_id, time.time() - time_start))

        flow.response = Response.fromJSON(response_json).toMITM()

