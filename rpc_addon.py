from http_proxy.log import Type, configure_logging
from http_proxy.rpc_client import HTTPProxyAddon
from unicornbottle.proxy import HTTPProxyClient

configure_logging(Type.PROXY)

http_proxy_client = HTTPProxyClient()
http_proxy_client.threads_start()

addons = [
    HTTPProxyAddon(http_proxy_client)
]
