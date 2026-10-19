"""同步 REST/Storage 请求复用连接；每次请求单独传凭据，防止串号。"""
import atexit
import io
import urllib.error

import httpx

_client = httpx.Client(
    timeout=20, follow_redirects=False,
    limits=httpx.Limits(max_connections=40, max_keepalive_connections=10, keepalive_expiry=30),
)
atexit.register(_client.close)


def supabase_urlopen(request, timeout=20):
    try:
        response = _client.request(
            request.get_method(), request.full_url,
            headers={**dict(request.header_items()), "Cookie": ""},
            content=request.data, timeout=timeout,
        )
    except httpx.HTTPError:
        # 不把包含请求头/正文的上游异常传播进日志。
        raise urllib.error.URLError("Supabase transport unavailable") from None
    if response.status_code >= 300:
        raise urllib.error.HTTPError(
            request.full_url, response.status_code, "Supabase request failed",
            response.headers, io.BytesIO(response.content),
        )
    return io.BytesIO(response.content)
