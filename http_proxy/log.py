import logging
import os

WORKER_LOG_FOLDER = '/var/log/ub-httpproxy-worker'
SERVER_LOG_FOLDER = '/var/log/ub-httpproxy-server'

def getLogger(name : str, worker : bool) -> logging.Logger:
    pid = os.getpid()

    if worker:
        log_folder = WORKER_LOG_FOLDER
    else:
        log_folder = SERVER_LOG_FOLDER

    file = "ub-httproxy-%s.log" % pid
    filename = "%s/%s" % (log_folder, file)
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(filename),logging.StreamHandler()])

    logger = logging.getLogger(name)

    return logger

