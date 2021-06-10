import unittest

class TestBase(unittest.TestCase):
    EXAMPLE_REQ = {
        "http_version": b"HTTP/1.1",
        "headers": (
            (b"User-Agent", b"Wget/1.21"),
            (b"Accept", b"*/*"),
            (b"Accept-Encoding", b"identity"),
            (b"Host", b"www.testing.local"),
            (b"Connection", b"Keep-Alive"),
            (b"Proxy-Connection", b"Keep-Alive"),
        ),
        "content": b"",
        "trailers": None,
        "timestamp_start": 1623276395.5825248,
        "timestamp_end": 1623276395.5842779,
        "host": "www.testing.local",
        "port": 80,
        "method": b"GET",
        "scheme": b"http",
        "authority": b"",
        "path": b"/",
    }

