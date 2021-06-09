import base64
import http_proxy
import json

class Request():
    def __init__(self, host:str, port:int, protocol:str, bytes:bytes) -> None:
        """
        Internal representation of request objects for the proxy and server instances.

        Args:
            host: hostname to connect to.
            port: port to connect to.
            protocol: either "http" or "https"
            bytes: the raw bytes of the request.
        """
        self.host = host
        self.port = port
        self.protocol = protocol
        self.bytes = base64.b64encode(bytes).decode('ascii')

    def toJSON(self) -> str:
        """
        Converts the object into a JSON string.
        """

        data = self.__dict__
        return json.dumps(data)

    @classmethod
    def fromJSON(cls, json_str : str):
        """
        Creates a Request object from a JSON string.

        Raises:
            json.decoder.JSONDecodeError: if you give it bad JSON.
        """
        j = json.loads(json_str)
        return cls(j['host'], j['port'], j['protocol'], base64.b64decode(j['bytes']))

