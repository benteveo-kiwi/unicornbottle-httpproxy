from unicornbottle.proxy import HTTPProxyClient
from mitmproxy.script import concurrent
import logging
import mitmproxy
import time
import uuid

logger = logging.getLogger(__name__)

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
        logger.error("EXITING CLEANLY due to Ctrl-C. Attempting to stop consuming queues.")
        if self.client.rabbit_connection is not None and self.client.channel is not None:
            self.client.rabbit_connection.add_callback_threadsafe(self.client.channel.stop_consuming)

        logger.info("Shutting down Postgres thread.")
        self.client.shutting_down = True

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


