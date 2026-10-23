"""Worker BYOK transport: HTTPS, pinned public DNS answers, no redirects."""
import http.client
import ipaddress
import socket
import urllib.request
import urllib.parse


def safe_urlopen(request, timeout=60):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("模型和图片下载只允许 HTTPS 公网地址")
    answers = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(item[4][0] for item in answers))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("模型地址不能访问本机、私有网络或保留地址")

    class PinnedConnection(http.client.HTTPSConnection):
        def connect(self):
            self.sock = socket.create_connection((addresses[0], self.port), timeout=self.timeout)
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)

    class PinnedHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(PinnedConnection, req)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("模型请求不能重定向，防止凭据泄漏")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PinnedHandler(), NoRedirect())
    return opener.open(request, timeout=timeout)
