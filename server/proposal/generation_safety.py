"""Shared handling for drafts whose review could not finish.

An incomplete review must not silently overwrite existing project content.
This check does not establish factual correctness when a review completes.
"""
from __future__ import annotations

from typing import Any


def review_incomplete(result: dict[str, Any]) -> bool:
    card = result.get("review_card")
    return bool(result.get("grounding_issues")) or bool(result.get("revision_incomplete")) or result.get("status") == "review_failed" or (
        isinstance(card, dict) and card.get("review_status") == "failed"
    )


def mark_review_alternative(result: dict[str, Any], version_id: str | None = None) -> None:
    result["review_incomplete"] = True
    result["conflict_status"] = "user_edit_preserved"
    if result.get("grounding_issues"):
        subject = "项目数据、成果或来源" if result.get("grounding_kind") == "project" else "部分个人数字"
        result["notice"] = (f"草稿中的{subject}需要你核对，已保留为备选，未覆盖当前正文。"
                            if version_id is not None else f"草稿中的{subject}需要你核对，未覆盖当前正文。")
    elif result.get("revision_incomplete"):
        result["notice"] = ("后续修改未完成，已保留上一版草稿为备选，未覆盖当前正文。"
                            if version_id is not None else "后续修改未完成，未覆盖当前正文。")
    else:
        result["notice"] = ("本轮检查未完成，草稿已保留为备选，未覆盖当前正文。"
                            if version_id is not None else "本轮检查未完成，未覆盖当前正文。")
    if version_id is not None:
        result["alternative_version_id"] = version_id


def mark_review_save_uncertain(result: dict[str, Any]) -> None:
    """Keep the returned content visible when storing its alternate failed."""
    result["review_incomplete"] = True
    result["result_save_uncertain"] = True
    result["conflict_status"] = "user_edit_preserved"
    if result.get("grounding_issues"):
        subject = "项目数据、成果或来源" if result.get("grounding_kind") == "project" else "部分个人数字"
        result["notice"] = f"草稿中的{subject}需要你核对；草稿保存状态不明，请先复制或放入编辑器，不必重复生成。"
    elif result.get("revision_incomplete"):
        result["notice"] = "后续修改未完成，上一版草稿保存状态不明，请先复制或放入编辑器，不必重复生成。"
    else:
        result["notice"] = "本轮检查未完成，草稿保存状态不明；请先复制或放入编辑器，不必重复生成。"
