from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any

from .agent import ModelUnavailable
from .workbench_metering import WorkbenchMeter
from .wopally_transport import wopally_urlopen


def generate_image(prompt: str, meter: WorkbenchMeter) -> bytes:
    """One bounded image request; only server-side credentials reach the relay."""
    request_id = meter.reserve("gpt-image-2", 1_000_000)
    request = urllib.request.Request(
        os.environ["WOPALLY_MODEL_BASE_URL"].rstrip("/") + "/images/generations",
        data=json.dumps({
            "model": "gpt-image-2", "prompt": prompt[:2000],
            "n": 1, "size": "1024x1024", "response_format": "b64_json",
        }, ensure_ascii=False).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['WOPALLY_WORKBENCH_API_KEY']}",
            "User-Agent": f"StardustWorkbench/{request_id}",
        },
        method="POST",
    )
    try:
        with wopally_urlopen(request, timeout=50) as response:
            body: Any = json.load(response)
    except urllib.error.HTTPError as exc:
        meter.refund(request_id)
        raise ModelUnavailable(f"生图服务返回 HTTP {exc.code}，本次预留已退回。") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # The provider may have generated an image despite a transport failure.
        # Keep the hold for usage-log reconciliation rather than charging twice.
        raise ModelUnavailable("生图结果暂未确认，本次积分预留正在核对。") from exc
    try:
        item = body["data"][0]
        image = base64.b64decode(item["b64_json"], validate=True)
        if len(image) > 12_000_000 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("invalid PNG")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ModelUnavailable("模型未返回有效 PNG，积分预留待核对。") from exc
    meter.settle(request_id, "gpt-image-2")
    return image
