import logging
import os

PROXY_LOG_FOLDER = '/var/log/ub-httpproxy-proxy'
SERVER_LOG_FOLDER = '/var/log/ub-httpproxy-server'

def getLogger(name : str, server : bool) -> logging.Logger:
    pid = os.getpid()

    if server:
        log_folder = SERVER_LOG_FOLDER
    else:
        log_folder = PROXY_LOG_FOLDER

    file = "ub-httproxy-%s.log" % pid
    filename = "%s/%s" % (log_folder, file)
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(filename),logging.StreamHandler()])

    logger = logging.getLogger(name)

    return logger

