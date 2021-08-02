from functools import partial
from http_proxy import log
from http_proxy.models import Request, Response
from io import BytesIO
from mitmproxy.script import concurrent
from sqlalchemy import select, and_
from sqlalchemy.orm.session import Session
from threading import Event, Thread
from typing import Dict, Optional, Any, Callable
from unicornbottle.database import database_connect, InvalidSchemaException
from unicornbottle.models import DatabaseWriteItem, RequestResponse, ExceptionSerializer, EndpointMetadata
from unicornbottle.rabbitmq import rabbitmq_connect
import base64
import logging
import mitmproxy
import pika
import queue
import sys
import threading
import time
import traceback
import uuid

logger = logging.getLogger(__name__)

class TimeoutException(Exception):
    pass

class NotConnectedException(Exception):
    pass

class UnauthorizedException(Exception):
    pass

class HTTPProxyClient(object):
    """
    This function implements the RPC model in a thread-safe way.
    """

    # Maximum time that we will wait for a `send_request` call.
    PROCESS_TIME_LIMIT = 15

    # Maximum amount of items that will be fetched from the queue prior to
    # writing.
    MAX_BULK_WRITE = 100

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
        self.db_write_queue : queue.SimpleQueue = queue.SimpleQueue()
        self.db_connections : dict[str, Session] = {}

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

    def thread_postgres_write(self, items_to_write:dict[str, list[RequestResponse]]) -> None:
        """
        Called when data is successfully read from the queue.

        Args:
            items_to_write: a dictionary containing lists of RequestResponses
                grouped by target_guids.
        """
        for target_guid in items_to_write:
            if target_guid not in self.db_connections:
                try:
                    self.db_connections[target_guid] = database_connect(target_guid, create=False)
                except InvalidSchemaException:
                    logger.error("Invalid schema %s in header." % target_guid)
                    continue

            logger.debug("Adding %s items for schema %s" % (len(items_to_write[target_guid]), target_guid))

            conn = self.db_connections[target_guid]

            for req_res in items_to_write[target_guid]:
                stmt = select(EndpointMetadata).where(and_(EndpointMetadata.pretty_url == req_res.pretty_url, # type:ignore 
                    EndpointMetadata.method == req_res.method))

                em = conn.execute(stmt).scalar()

                if em is None:
                    em = EndpointMetadata(pretty_url=req_res.pretty_url, method=req_res.method)
                    conn.add(em)
                    conn.commit()

                print(req_res.id, req_res.pretty_url, req_res.metadata_id, em)
                req_res.metadata_id = em.id

                conn.add(req_res)

            conn.commit()

    def thread_postgres_read_queue(self) -> None:
        """
        This function gets called periodically by `self.thread_postgres`.
        Handles a single iteration of reading from the queue.
        """
        items_to_write : Dict[str, list[RequestResponse]] = {}
        items_read = 0
        try:
            while items_read < self.MAX_BULK_WRITE:
                dwi = self.db_write_queue.get_nowait()
                if dwi.target_guid not in items_to_write:
                    items_to_write[dwi.target_guid] = []

                items_to_write[dwi.target_guid].append(RequestResponse.createFromDWI(dwi))
                items_read += 1
        except queue.Empty:
            pass

        if items_read > 0:
            logger.debug("Writing %s requests to database." % items_read)
            self.thread_postgres_write(items_to_write)

    def thread_postgres(self) -> None:
        """
        Main thread for connections to PostgreSQL and regular insertion of
        rows.

        A queue of request/responses pending writes, located at
        `self.db_write_queue`, is regularly popped in this function.

        The general idea is that writes are handled outside of the mitmdump
        thread so that database writes do not influence the proxy's response
        speed times. One connection per database schema is maintained, for more
        information see `unicornbottle.database`.
        """
        logger.info("PostgreSQL thread starting")
        try:
            while True:
                self.thread_postgres_read_queue()

                time.sleep(0.05)
        except:
            logger.exception("Exception in PostgreSQL thread")
            raise
        finally:
            logger.error("PostgreSQL thread is shutting down. See log for details.")
            for conn in self.db_connections:
                self.db_connections[conn].close()

            self.db_connections = {}

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

            logger.info("RabbitMQ thread ready to start consuming")
            self.channel.start_consuming() 
        except:
            logger.exception("Exception in RabbitMQ thread")
            raise
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

    def target_guid_valid(self, val:str) -> bool:
        """
        Simple utility function to perform basic checks on the user-provided
        UUID.

        Args:
            val: the value to check.

        See:
            https://stackoverflow.com/a/54254115
        """
        try:
            uuid.UUID(str(val))
            return True
        except ValueError:
            return False

    def target_guid(self, request:mitmproxy.net.http.Request) -> str:
        """
        Obtain target guid from request.

        Args:
            request: the request to get the target_guid from.

        Returns:
            the target GUID.
        """
        exc = UnauthorizedException("Missing required authentication headers.")
        try:
            target_guid = request.headers['X-UB-GUID']
            if not self.target_guid_valid(target_guid):
                raise exc
        except KeyError:
            raise exc

        return str(target_guid)

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
            UnauthorizedException: Missing or malformed X-UB-GUID header. This
                serves as a form of precarious auth.
        """
        target_guid = self.target_guid(request)

        try:
            if not self.threads_alive() or (self.rabbit_connection is None or self.channel is None):
                logger.error("One or more threads are dead. Attempting to restart and sending error to client.")
                self.threads_start()
                raise NotConnectedException("Not connected. Please retry in a jiffy.") # still raise. Clients must retry.

            self.corr_ids[corr_id] = True

            message_body = Request(request.get_state()).toJSON() # type:ignore
            basic_pub = partial(self.channel.basic_publish, exchange='', routing_key='rpc_queue',
                properties=pika.BasicProperties(reply_to=self.callback_queue, correlation_id=corr_id,),
                body=message_body)
            self.rabbit_connection.add_callback_threadsafe(basic_pub)

            response = self.get_response(corr_id)
        except Exception as e:
            # Couldn't successfully retrieve a response for this request. Still write to DB.
            exc_info = ExceptionSerializer(type(e).__name__, str(e), traceback.format_exc())
            dwr = DatabaseWriteItem(target_guid, request, response=None, exception=exc_info)
            self.db_write_queue.put(dwr)

            raise
        else:
            dwr = DatabaseWriteItem(target_guid, request, response, exception=None)
            self.db_write_queue.put(dwr)

        return response

    def get_response(self, corr_id:str) -> mitmproxy.net.http.Response:
        """
        This function reads from `self.responses[corr_id]` in a BLOCKING
        fashion until either a response is populated by the queue reader or
        `self.PROCESS_TIME_LIMIT` is exceeded.

        `self.responses` is populated by `self.on_response()`.

        Args:
            corr_id: The correlation ID for this request.
        """
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
        return self._request(flow)

    def _request(self, flow: mitmproxy.http.HTTPFlow) -> None:
        """
        Same as _request but without the wrapper to facilitate testing.

        Args:
            flow: the flow for this request. At this stage, flow.response is
                not yet set, but will be set by this function.
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
            flow.response = mitmproxy.http.HTTPResponse.make(502, b"502 Exception")


