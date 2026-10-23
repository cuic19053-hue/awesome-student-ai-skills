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
    image, request_id = generate_image_deferred(prompt, meter)
    meter.settle(request_id, "gpt-image-2")
    return image


def generate_image_deferred(
    prompt: str, meter: WorkbenchMeter, *, request_timeout: int = 50
) -> tuple[bytes, str]:
    """Generate once and return the reservation ID for an external settlement step.

    The cloud Worker proxy uses this form so image generation and usage-log
    reconciliation can run in separate bounded Vercel requests.
    """
    # Auto quality can select high; reserve enough for the published 1024px
    # high-quality output plus text input at the fixed official-price FX.
    request_id = meter.reserve("gpt-image-2", 2_000_000)
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
        with wopally_urlopen(request, timeout=request_timeout) as response:
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
    return image, request_id


def generate_custom_image(
    prompt: str, base_url: str, model: str, api_key: str, *, opener=None, timeout: int = 60
) -> bytes:
    """Generate an image using user-supplied OpenAI-compatible image endpoint (0 credits)."""
    endpoint = base_url.rstrip("/") + "/images/generations"
    open_request = opener or urllib.request.urlopen
    payload: dict[str, Any] = {
        "model": model or "dall-e-3",
        "prompt": prompt[:2000],
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}",
        "User-Agent": "StardustWorkbench/BYOK-Image",
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with open_request(request, timeout=timeout) as response:
            body: Any = json.load(response)
    except urllib.error.HTTPError as exc:
        err_msg = ""
        try:
            err_data = json.loads(exc.read().decode())
            err_msg = (
                err_data.get("error", {}).get("message")
                or err_data.get("message")
                or str(err_data)
            )
        except Exception:
            pass
        raise ModelUnavailable(f"自定义生图服务返回 HTTP {exc.code}：{err_msg or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ModelUnavailable(f"无法连接自定义生图服务：{str(exc)}") from exc

    try:
        data_list = body.get("data")
        if not isinstance(data_list, list) or not data_list:
            raise ValueError("返回数据缺少 data 列表")
        item = data_list[0]
        if "b64_json" in item and item["b64_json"]:
            image = base64.b64decode(item["b64_json"], validate=True)
        elif "url" in item and item["url"]:
            img_url = item["url"]
            img_req = urllib.request.Request(img_url, headers={"User-Agent": "StardustWorkbench/1.0"})
            with open_request(img_req, timeout=30) as img_resp:
                image = img_resp.read()
        else:
            raise ValueError("未返回有效图片数据 (缺少 b64_json 或 url)")
        if len(image) < 100:
            raise ValueError("图片数据无效")
        if len(image) > 15_000_000:
            raise ValueError("图片数据超过 15MB 限制")
        return image
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ModelUnavailable(f"未能解析生图结果：{str(exc)}") from exc
