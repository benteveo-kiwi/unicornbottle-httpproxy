from http_proxy.rpc_client import HTTPProxyAddon
from http_proxy.log import Type, configure_logging

if __name__ == "__main__":
    configure_logging(Type.PROXY)

addons = [
    HTTPProxyAddon()
]
