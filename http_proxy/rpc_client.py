from functools import partial
from unicornbottle.rabbitmq import rabbitmq_connect
from unicornbottle.database import database_connect
from http_proxy import log
from http_proxy.models import Request, Response
from io import BytesIO
from mitmproxy.script import concurrent
from threading import Event, Thread
from typing import Dict, Optional, Any, Callable
import base64
import logging
import mitmproxy
import pika
import sys
import threading
import time
import uuid

logger = logging.getLogger(__name__)

class TimeoutException(Exception):
    pass

class NotConnectedException(Exception):
    pass

class HTTPProxyClient(object):
    """
    This function implements the RPC model in a thread-safe way.
    """

    # Maximum time that we will wait for a `call`.
    PROCESS_TIME_LIMIT = 15

    def __init__(self) -> None:
        """
        Main constructor. `threads_start()` should normally be called by the
        instantiator immediately after construction.
        """
        self.lock = threading.Lock()

        self.rabbit_connection : Optional[pika.BlockingConnection] = None
        self.channel : Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self.threads : Dict[Callable, threading.Thread] = {}

        self.corr_ids : Dict[str, bool] = {}
        self.responses : Dict[str, bytes] = {}

    def threads_start(self) -> None:
        """
        Spawn the required threads and store them in self.threads. If the
        thread is already present in that dictionary, we check whether it's
        alive and if not we restart it. 

        This function is called both at startup and in the event a thread dies.

        - RabbitMQ connection thread.
        - PostgreSQL writer thread.
        """
        req_targets = [self.thread_rabbit, self.thread_postgres]
        
        for target in req_targets:
            if target in self.threads and self.threads[target].is_alive():
                continue

            self.threads[target] = self.thread_spawn(target=target,
                    name=target.__name__)

    def threads_alive(self) -> bool:
        """
        Checks that all threads are currently alive.

        Returns:
            bool: True if all threads are alive, False if at least one thread
                is currently dead.
        """
        
        if len(self.threads) == 0:
            return False

        for thread in self.threads.values():
            if not thread.is_alive():
                return False

        return True

    def thread_spawn(self, target:Callable, name:str) -> threading.Thread:
        """
        Spawns a thread that calls the callable.

        Args:
            @see https://docs.python.org/3/library/threading.html#threading.Thread

        Return: 
            thread: the newly started thread.
        """
        thread = threading.Thread(target=target, name=name)
        thread.start()

        return thread

    def thread_postgres(self) -> None:
        """
        Manages the connections to PostgreSQL and regular insertion of rows.

        A queue of request/responses pending writes, located at
        `self.db_write_queue`, is regularly popped in this function.

        The general idea is that writes are handled outside of the mitmdump
        thread so that database writes do not influence the proxy's response
        speed times. One connection per database schema is maintained, for more
        information see `unicornbottle.database`.
        """
        try:
            while True:
                time.sleep(1)
        except:
            logger.exception("Exception in PostgreSQL thread")
        finally:
            logger.error("PostgreSQL thread is shutting down. See log for details.")

    def thread_rabbit(self) -> None:
        """
        Initializes the responses queue and handles consumption of responses.
        This is a blocking function and should be called in a new Thread.
        """
        try:
            self.rabbit_connection = rabbitmq_connect()
            self.channel = self.rabbit_connection.channel()

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
            logger.exception("Exception in RabbitMQ thread")
        finally:
            logger.error("RabbitMQ thread is shutting down. See log above for details.")
            if self.rabbit_connection:
                self.rabbit_connection.close()

            # Ensure variables are unset if threads die.
            self.rabbit_connection = None
            self.channel = None

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

    def send_request(self, request : mitmproxy.net.http.Request, corr_id : str) -> mitmproxy.net.http.Response:
        """
        Serialize and send the request to RabbitMQ, receive the response and
        unserialize.

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
            request: A mitmproxy Request object.
            corr_id: the correlation id for this request, a uuid.

        Raises:
            TimeoutException: self.PROCESS_TIME_LIMIT exceeded, request timeout.
            NotConnectedException: We're currently not connected to AMQ. Will
                attempt to reconnect so that next `call` is successful.
        """
        message_body = Request(request.get_state()).toJSON() # type:ignore

        if not self.threads_alive() or (self.rabbit_connection is None or self.channel is None):
            logger.error("One or more threads are dead. Attempting to restart and sending error to client.")
            self.threads_start()
            raise NotConnectedException("Not connected. Please retry in a jiffy.") # still raise. Clients must retry.

        self.corr_ids[corr_id] = True

        basic_pub = partial(self.channel.basic_publish, exchange='', routing_key='rpc_queue',
            properties=pika.BasicProperties(reply_to=self.callback_queue, correlation_id=corr_id,),
            body=message_body)

        self.rabbit_connection.add_callback_threadsafe(basic_pub)

        start = time.time()
        try:
            while True:
                resp = None
                try:
                    resp = self.responses[corr_id]
                except KeyError:
                    pass

                timeout = time.time() - start >= self.PROCESS_TIME_LIMIT

                if not resp and timeout:
                    raise TimeoutException
                elif resp:
                    return Response.fromJSON(self.responses[corr_id]).toMITM()

                time.sleep(0.001) 
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

    def __init__(self, client : HTTPProxyClient):
        logger.info("Mitmproxy addon started.")

        self.client : HTTPProxyClient = client

        logger.info("Established connection to RabbitMQ.")

    def done(self) -> None:
        """
        Called when mitmproxy exits.
        """
        logger.info("Exiting cleanly. Attempting to stop consuming queues.")

        if self.client.rabbit_connection is not None and self.client.channel is not None:
            self.client.rabbit_connection.add_callback_threadsafe(self.client.channel.stop_consuming)

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

            flow.response = self.client.send_request(flow.request, corr_id)
            time_handled = time.time() - time_start

            logger.debug("%s:Done handling request. Total time %s seconds" % (corr_id, time.time() - time_start))
        except:
            logger.exception("Unhandled exception in request thread.", exc_info=True)
            flow.response = mitmproxy.http.HTTPResponse.make(502, b"HTTP Proxy unhandled exception")


