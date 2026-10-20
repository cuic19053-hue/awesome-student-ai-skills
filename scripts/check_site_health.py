"""外部存活拨测：只访问无副作用的生产 ping，不调用模型或数据库。"""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

URL = "https://agent.stardust.website/api/ping"


def check(attempts=3):
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            request = urllib.request.Request(URL, headers={"User-Agent": "Stardust-Uptime/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status != 200 or json.loads(response.read(4096)).get("status") != "ok":
                    raise ValueError("unexpected response")
            print(f"健康检查通过，响应耗时 {time.monotonic() - started:.2f}s")
            return True
        except (OSError, ValueError, urllib.error.URLError):
            print(f"健康检查第 {attempt + 1} 次失败")
            if attempt + 1 < attempts:
                time.sleep(2 ** (attempt + 1))
    return False


if __name__ == "__main__":
    ok = check()
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as handle:
            handle.write(f"## 生产站点健康检查\n\n{'✅ 正常' if ok else '❌ 连续三次未通过'}\n")
    raise SystemExit(0 if ok else 1)
