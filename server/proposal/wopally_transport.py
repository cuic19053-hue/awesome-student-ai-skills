from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a fixed origin while verifying its public DNS TLS identity."""

    def __init__(self, host: str, *, origin_ip: str, **kwargs: Any):
        super().__init__(host, **kwargs)
        self._origin_ip = origin_ip

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._origin_ip, self.port), self.timeout, self.source_address
        )
        try:
            # The original Host and SNI remain api.wopally.cn. The default SSL
            # context verifies the certificate; do not use an unverified one.
            self.sock = self._context.wrap_socket(sock, server_hostname="api.wopally.cn")
        except BaseException:
            sock.close()
            raise


class _PinnedHandler(urllib.request.HTTPSHandler):
    def __init__(self, origin_ip: str):
        super().__init__(context=ssl.create_default_context())
        self.origin_ip = origin_ip

    def https_open(self, request: urllib.request.Request):
        return self.do_open(
            lambda host, **kwargs: _PinnedHTTPSConnection(
                host, origin_ip=self.origin_ip, **kwargs
            ),
            request,
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(request.full_url, code, "Upstream redirect refused", headers, fp)


def wopally_urlopen(request: urllib.request.Request, timeout: int = 10):
    origin_ip = os.environ.get("WOPALLY_ORIGIN_IP", "").strip()
    if not origin_ip:
        return urllib.request.urlopen(request, timeout=timeout)
    parsed = urllib.parse.urlparse(request.full_url)
    if parsed.scheme != "https" or parsed.hostname != "api.wopally.cn" or parsed.port not in (None, 443):
        raise ValueError("Pinned Wopally transport only accepts the verified HTTPS host")
    ip = ipaddress.ip_address(origin_ip)
    if not ip.is_global:
        raise ValueError("Wopally origin must be a public IP")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _PinnedHandler(str(ip)), _NoRedirect())
    return opener.open(request, timeout=timeout)
