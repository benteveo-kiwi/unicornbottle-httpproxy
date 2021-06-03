# HTTP Proxy

This is an HTTP proxy that distributes requests over a number of workers. This
is achieved by sending the HTTP requests to a RabbitMQ queue, where it is
picked up by a number of workers.

# Installation

```
pip install -r requirements.txt requirements_test.txt
```

# To run:

```
mitmdump --no-http2 -s rpc_addon.py
```

I disable HTTP2 because I don't need that kind of functionality and it could be
error prone if implemented incorrectly. Most people wouldn't expect an HTTP
proxy to support HTTP2 in any case so it shoud work OK.


# Run unit tests:

```
python3 -m unittest http_proxy.test_http_proxy
```

To run an individual test:

```
python3 -m unittest http_proxy.test_http_proxy.TestHttpProxy.test_request_method
```

# Type Checking

The code within this repository supports type checking. This should prevent
dumb errors that can easily be avoided by it. You can install the pre-commit
hook by running the following command:

```
cp pre_commit_hook/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

You can also run static type checks with: 

```
mypy http_proxy/ rpc_addon.py --exclude 'test.*' --ignore-missing-imports`
```
