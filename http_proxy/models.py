from typing import Dict, Optional, Any, Union, TypeVar, Type
import base64
import http_proxy
import json
import mitmproxy.net.http

MS = TypeVar('MS', bound='MessageSerializer')

class RequestEncoder(json.JSONEncoder):
    """
    Performs encoding of byte arrays as base64. The rationale for doing this is
    to prevent having to deal with every known encoding known in the universe
    and instead transmit bytes as they are.

    Byte arrays that are encoded are prefixed by "application/base64:" in order
    to facilitate detection of base64 by the decoder.
    """
    def default(self, obj : Any) -> Any:
        if isinstance(obj, (bytes, bytearray)):
            encoded = base64.b64encode(obj).decode("ascii")
            return "application/base64:" + encoded

        return json.JSONEncoder.default(self, obj)

class RequestDecoder(json.JSONDecoder):
    """
    Decodes requests encoded by RequestEncoder.

    Recursively iterates through all objects and decodes strings if they match
    the required prefix.
    """
    def __init__(self, *args, **kwargs) -> None: #type:ignore
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def decode_base64(self, string : str) -> Union[str, bytes]:
        """
        Decodes strings and returns the corresponding bytes if they are base64
        
        Args:
            string: the input string decode or leave as is.
        """
        if string.startswith("application/base64:"):
            splat = string.split(":")
            return base64.b64decode(splat[1])
        else:
            return string

    def object_hook(self, data : Any) -> Any:
        if isinstance(data, (dict, list)):
            for k, v in (data.items() if isinstance(data, dict) else enumerate(data)):
                if isinstance(v, str):
                    data[k] = self.decode_base64(v)

                self.object_hook(v)

        return data

class MessageSerializer():
    def __init__(self, state : dict) -> None:
        """
        Internal representation of request/response objects for the proxy and
        server instances. Can be used to transmit mitmproxy's internal
        representations.

        Args:
            state: request state as exported by the
                mitmproxy.Request.get_state() method.
        """

        self.state = state

    def toJSON(self) -> str:
        """
        Converts the object into a JSON string. Byte arrays are encoded into
        base64.
        """

        data = self.state
        return json.dumps(data, cls=RequestEncoder)

    @classmethod
    def fromJSON(cls : Type[MS], json_str : bytes) -> MS:
        """
        Creates a Request object from a JSON string.

        Raises:
            json.decoder.JSONDecodeError: if you give it bad JSON.
        """
        j = json.loads(json_str)
        state = json.loads(json_str, cls=RequestDecoder)
        return cls(state)


class Request(MessageSerializer):
    def toMITM(self) -> mitmproxy.net.http.Request:
        """
        Grabs data stored in the request state and converts it into a mitmproxy.http.Request object.
        """
        return mitmproxy.net.http.Request(**self.state)

class Response(MessageSerializer):
    def toMITM(self) -> mitmproxy.net.http.Response:
        """
        Grabs data stored in the request state and converts it into a mitmproxy.http.Response object.
        """
        return mitmproxy.net.http.Response(**self.state)


