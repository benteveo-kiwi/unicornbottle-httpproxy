import logging
import os
import sys
from enum import Enum

PROXY_LOG_FOLDER = '/var/log/ub-httpproxy-proxy'
WORKER_LOG_FOLDER = '/var/log/ub-httpproxy-worker'

class Type(Enum):
    """
    What type of process are we currently running as. This can be one of three:

    1. Proxy. We have been started as `service httpproxy start` and are
        listening on port 8080 for connections and sending them to the queue.
    2. Worker. We are one of the worker instances currently waiting for
        messages from the queue.
    3. Test. We're inside the test suite.
    """
    PROXY = 1
    WORKER = 2
    TEST = 3

class IDNotSetException(Exception):
    pass

def configure_logging(type : Type, id : int = -1) -> None:
    """
    Instantiates the appropriate logger for this instance based on parameters.

    Args:
        type: Type of logger. See http_proxy.log.Type
        id: An integer between one and ten which is used to differentiate
            between worker processes. Only used if Type.Proxy.
    """
    if type == Type.WORKER:

        if id == -1:
            raise IDNotSetException("Worker threads require an ID to prevent\
                    race conditions in logging.")

        log_folder = WORKER_LOG_FOLDER
        file = "ub-worker-%s.log" % str(id)
        filename = "%s/%s" % (log_folder, file)
    else:
        log_folder = PROXY_LOG_FOLDER
        filename = "%s/%s" % (log_folder, "ub-httpproxy.log")
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s",
        handlers=[logging.FileHandler(filename),logging.StreamHandler()])

    logging.getLogger("pika").setLevel(logging.WARNING)

