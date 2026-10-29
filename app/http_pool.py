"""Stateless requests with connection reuse across short-lived background workers.

Sessions own mutable cookies, authentication and headers, so each call gets its own.
Only the thread-safe urllib3 connection pools are shared. This keeps provider credentials
request-scoped while avoiding a new TCP/TLS connection for every AI request.
"""
import atexit

import requests
from requests.adapters import HTTPAdapter

exceptions = requests.exceptions
_adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
atexit.register(_adapter.close)


def request(method, url, **kwargs):
    session = requests.Session()
    session.mount("http://", _adapter)
    session.mount("https://", _adapter)
    try:
        return session.request(method, url, **kwargs)
    finally:
        # Session.close must not close the shared pools used by other workers.
        session.adapters.clear()
        session.close()


def post(url, **kwargs):
    return request("POST", url, **kwargs)


def get(url, **kwargs):
    return request("GET", url, **kwargs)
