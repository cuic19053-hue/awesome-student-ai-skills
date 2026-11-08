"""Short, context-bound clarification for the innovation competition."""
from __future__ import annotations

import re


INTERNET_TRACK_QUESTION = (
    "你准备参加高教主赛道、职教赛道，还是青年红色筑梦之旅（红旅）？"
    "如果还不确定，也可以先说说项目的服务对象和实践情况。"
)


def is_track_choice(text: str) -> bool:
    """Only attach prior competition context to an actual track answer."""
    return bool(re.search(r"高教主赛道|高教赛道|职教赛道|职教主赛道|主赛道|红色之旅|红旅|红色筑梦之旅", text))


def should_ask_internet_track(text: str, route: dict) -> bool:
    """Ask before selecting when the competition has multiple possible tracks."""
    if route.get("selected") or not route.get("needs_clarification"):
        return False
    candidates = {candidate.get("name") for candidate in route.get("candidates", [])}
    if not {"internet-plus", "internet-plus-red-tour"}.issubset(candidates):
        return False
    if re.search(r"(?:哪些|有什么|介绍|区别|如何选择|怎么选择|怎么选|怎样选).{0,8}(?:赛道|主赛道|红旅)|"
                 r"(?:赛道|主赛道|红旅).{0,8}(?:有哪些|有什么|区别|怎么选|如何选择)", text):
        return False
    return True
