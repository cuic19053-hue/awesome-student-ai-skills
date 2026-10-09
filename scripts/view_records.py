#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后台项目对话审计与 Token 成本分析工具。"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / ".agent-data" / "agent.sqlite3"


def view_records(project_id: str | None = None) -> None:
    if not DB_PATH.exists():
        print(f"[-] 数据库不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. 查询全局 Token 概况
    cursor.execute("""
        SELECT
            COUNT(*),
            COALESCE(SUM(prompt_tokens), 0),
            COALESCE(SUM(completion_tokens), 0),
            COALESCE(SUM(total_tokens), 0),
            COALESCE(AVG(latency_ms), 0)
        FROM token_usages
    """)
    g_count, g_prompt, g_comp, g_total, g_latency = cursor.fetchone()

    print("=" * 76)
    print(" 🌟 STARDUST AGENT · LLM 可观测性与 Token 成本审计控制台")
    print("=" * 76)
    print(f"📊 全局统计: 累计调用 {g_count} 次 | 总 Token: {g_total:,} (输入: {g_prompt:,} / 输出: {g_comp:,}) | 平均时延: {g_latency:.0f}ms")
    print("=" * 76)

    # 2. 查询项目列表
    if project_id:
        cursor.execute("SELECT id, title, level, discipline, school, state_json, updated_at FROM projects WHERE id = ?", (project_id,))
    else:
        cursor.execute("SELECT id, title, level, discipline, school, state_json, updated_at FROM projects ORDER BY updated_at DESC")
    projects = cursor.fetchall()

    if not projects:
        print("[!] 暂无项目记录。")
        conn.close()
        return

    for p_id, title, level, discipline, school, state_json, updated_at in projects:
        state = json.loads(state_json or "{}")
        model_cfg = state.get("last_model_config", {})

        # 该项目的 Token 统计
        cursor.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(prompt_tokens), 0),
                COALESCE(SUM(completion_tokens), 0),
                COALESCE(SUM(total_tokens), 0),
                COALESCE(AVG(latency_ms), 0)
            FROM token_usages WHERE project_id = ?
        """, (p_id,))
        p_count, p_prompt, p_comp, p_total, p_lat = cursor.fetchone()

        # 各任务分布
        cursor.execute("""
            SELECT task_type, COUNT(*), SUM(total_tokens)
            FROM token_usages WHERE project_id = ? GROUP BY task_type
        """, (p_id,))
        task_breakdown = cursor.fetchall()

        print(f"\n📂 课题档案: {title or '未命名'} (ID: {p_id})")
        print(f"   申报级别: {level or '未设置'} | 学科: {discipline or '未设置'} | 高校: {school or '未设置'}")
        print(f"   最后活跃: {updated_at}")
        if model_cfg:
            print(f"   ⚙️ 当前模型: {model_cfg.get('provider')} · {model_cfg.get('model')} ({model_cfg.get('base_url') or '本地'}) | 密钥掩码: {model_cfg.get('key_hint', '—')}")
        else:
            print("   ⚙️ 当前模型: 本地默认 (Ollama / qwen2.5:7b)")

        task_str = " | ".join(f"{t}: {cnt}次({tok:,} tok)" for t, cnt, tok in task_breakdown) if task_breakdown else "暂无记录"
        print(f"   ⚡ Token 消耗: 累计 {p_total:,} Tokens (输入: {p_prompt:,} / 输出: {p_comp:,} / 调用: {p_count}次 / 均延: {p_lat:.0f}ms)")
        print(f"   📋 任务分布: {task_str}")

        # Token 节省建议诊断
        if p_count > 0:
            avg_prompt = p_prompt / p_count
            saving_hints = []
            if avg_prompt > 1500:
                saving_hints.append("每轮输入 Prompt 偏大(>1.5k)，建议对 RAG 检索材料增加相似度阈值过滤(Top-3)")
            if p_total > 8000:
                saving_hints.append("长会话累计 Token 较高，建议启用对话历史滑动窗口压缩")
            if not saving_hints:
                saving_hints.append("Token 消耗在健康合理区间")
            print(f"   💡 成本诊断: {'; '.join(saving_hints)}")

        # 对话记录
        cursor.execute("SELECT role, content, created_at FROM messages WHERE project_id = ? ORDER BY created_at ASC", (p_id,))
        messages = cursor.fetchall()
        print(f"   💬 对话记录: 共 {len(messages)} 轮")
        print("   " + "-" * 70)

        for role, content, created_at in messages:
            role_tag = "👤 [学生/用户]" if role == "user" else "🤖 [Stardust Agent]"
            preview = content.strip().replace("\n", "\n      ")
            print(f"   {role_tag} ({created_at}):")
            print(f"      {preview}\n")

    conn.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    view_records(target)
