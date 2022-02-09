from mitmproxy.script import concurrent
from unicornbottle.database_models import STATIC_FILES
from unicornbottle.proxy import HTTPProxyClient
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
        logger.error("EXITING CLEANLY due to Ctrl-C.")
        self.client.threads_shutdown()

    def is_very_clearly_static(self, pretty_url:str) -> bool:
        """
        Returns whether we can tell that it's a static file we don't care about
        just by looking at the URL.

        Args:
            pretty_url: the request pretty_url as defined by mitmproxy.
        """
        for static_ending in STATIC_FILES:
            static_ending = static_ending[1:] # Remove starting %.
            if pretty_url.endswith(static_ending):
                return True

        return False

    @concurrent # type: ignore
    def request(self, flow: mitmproxy.http.HTTPFlow) -> None:
        """
        Main mitmproxy entry point. This function gets called on each request
        received after mitmproxy handles all the underlying HTTP shenanigans.

        For more documentation, you can run the following command:

        pydoc3 mitmproxy.http
        pydoc3 mitmproxy.net.http.request
        """
        
        # Skip static files that we don't care about.
        if not self.is_very_clearly_static(flow.request.pretty_url):
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


