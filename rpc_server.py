from http_proxy import rpc_server
from http_proxy.log import Type, configure_logging
import sys

if __name__ == "__main__":
    configure_logging(Type.WORKER, int(sys.argv[1]))
    rpc_server.listen()
