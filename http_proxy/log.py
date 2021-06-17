import logging
import os

PROXY_LOG_FOLDER = '/var/log/ub-httpproxy-proxy'
SERVER_LOG_FOLDER = '/var/log/ub-httpproxy-worker'

def getLogger(name : str, server : bool) -> logging.Logger:
    pid = os.getpid()

    if server:
        log_folder = SERVER_LOG_FOLDER
        file = "ub-worker-%s.log" % pid
        filename = "%s/%s" % (log_folder, file)
    else:
        log_folder = PROXY_LOG_FOLDER
        filename = "%s/%s" % (log_folder, "ub-httpproxy.log")
    
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s]: %(message)s",
        handlers=[logging.FileHandler(filename),logging.StreamHandler()])

    logging.getLogger("pika").setLevel(logging.WARNING)

    logger = logging.getLogger(name)

    return logger

