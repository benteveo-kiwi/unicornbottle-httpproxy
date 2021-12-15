# HTTP Proxy

This is an HTTP proxy that distributes requests over a number of workers. These
workers are also stored within this repository, and are run with the
`rpc_server.py` command. See below for info. This is achieved by sending the
HTTP requests to a RabbitMQ queue, where it is picked up by a number of
workers.

# Cloning.

This module uses `git submodules` to share code with other repositories. In order to clone those as well use the following command:

```
git clone --recurse-submodules <URL>
```

# Installation & Python dependencies.

Please see unicornbottle-dev/README.md for more info.

# To run:

```
sudo -u httpproxy mitmdump --set confdir=/opt/mitmdump --no-http2 -s rpc_addon.py
```

I disable HTTP2 because I don't need that kind of functionality and it could be
error prone if implemented incorrectly. Most people wouldn't expect an HTTP
proxy to support HTTP2 in any case so it shoud work OK.

To run the worker thread, run as follows:

```
sudo -u httpproxy python3 rpc_server.py 1337 # 1337 is a log file number.
```


# Run unit tests:

```
pytest
```

To run an individual test:

```
pytest -s -k "test_db_write"
```

