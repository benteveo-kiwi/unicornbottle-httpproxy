from typing import Dict, Optional, Any
import base64
import http_proxy
import json

class Request():
    def __init__(self, host:str, port:int, protocol:str, encoded_bytes:str) -> None:
        """
        Internal representation of request objects for the proxy and server instances.

        Args:
            host: hostname to connect to.
            port: port to connect to.
            protocol: either "http" or "https"
            encoded_bytes: the raw bytes of the request as an ascii string.
        """
        self.host = host
        self.port = port
        self.protocol = protocol
        self.encoded_bytes = encoded_bytes

    def toJSON(self) -> str:
        """
        Converts the object into a JSON string.
        """

        data = self.__dict__
        return json.dumps(data)

    @classmethod
    def fromJSON(cls, json_str : bytes):
        """
        Creates a Request object from a JSON string.

        Raises:
            json.decoder.JSONDecodeError: if you give it bad JSON.
        """
        j = json.loads(json_str)
        return cls(j['host'], j['port'], j['protocol'], j['encoded_bytes'])

