#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/sync_douyin_stats.py
定时抓取/同步抖音视频（点赞数、收藏数、分享数）到 README.md 与 README_EN.md
"""

import sys
import os
import json
import re
import argparse
from datetime import datetime

VIDEO_ID = "7692700167341985051"
VIDEO_URL = f"https://www.douyin.com/video/{VIDEO_ID}"
STATS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "douyin_stats.json")
README_CN = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
README_EN = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README_EN.md")


def format_number(num: int) -> str:
    """格式化数字为千位或万位标签，如 8039 -> 8000+, 12500 -> 1.2w+"""
    if num >= 10000:
        val = num / 10000.0
        return f"{val:.1f}w+"
    elif num >= 1000:
        val = round(num / 100.0) * 100
        return f"{val}+"
    else:
        return f"{num}+"


def fetch_stats_via_playwright() -> dict:
    """使用 Playwright 无头浏览器加载视频页面并提取真实统计数字"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[Warning] 未安装 playwright，无法自动爬取。可在 CI 环境通过 pip install playwright 安装。")
        return {}

    stats = {}
    print(f"[Info] 启动 Playwright 抓取: {VIDEO_URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            page.goto(VIDEO_URL, timeout=30000, wait_until="domcontentloaded")
            # 等待前端异步拉取并渲染点赞/收藏数字
            page.wait_for_timeout(4000)

            # 抓取页面所有的数字项
            digits = page.evaluate("""() => {
                let items = Array.from(document.querySelectorAll('*'))
                    .filter(el => el.children.length === 0 && el.textContent.trim().length > 0)
                    .map(el => el.textContent.trim())
                    .filter(t => /^\\d+(\\.\\d+)?(w|万|\\+)?$/.test(t));
                return items;
            }""")

            print(f"[Info] 抓取到候选数字: {digits[:15]}")

            # 抖音视频详情页通常依次为：点赞数、评论数、收藏数、分享数
            # 过滤掉为 0 的异常项，提取合理区间的数值
            candidates = []
            for d in digits:
                if d.isdigit() and int(d) > 50:
                    candidates.append(int(d))

            if len(candidates) >= 3:
                # 一般点赞数在最前面，数值较大
                likes = max(candidates[:2])
                collects = candidates[2] if len(candidates) > 2 else 0
                shares = candidates[3] if len(candidates) > 3 else 0
                stats = {
                    "likes": likes,
                    "collects": collects,
                    "shares": shares,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                print(f"[Success] 解析数据成功: {stats}")
            else:
                print(f"[Warning] 候选数字不足，可能需要人机验证或页面改版: {candidates}")

        except Exception as e:
            print(f"[Error] Playwright 抓取异常: {e}")
        finally:
            browser.close()

    return stats


def update_readme_files(stats: dict):
    """根据最新 stats 更新 README.md 与 README_EN.md"""
    likes_str = format_number(stats.get("likes", 8000))
    collects_str = format_number(stats.get("collects", 6000))
    shares_str = format_number(stats.get("shares", 1400))

    print(f"[Info] 准备同步到文档: 获赞={likes_str}, 收藏={collects_str}, 转发={shares_str}")

    # 更新中文 README.md
    if os.path.exists(README_CN):
        with open(README_CN, "r", encoding="utf-8") as f:
            content = f.read()

        # 正则替换 Badge
        content = re.sub(
            r'\[!\[Douyin Likes\]\(https://img\.shields\.io/badge/抖音获赞-[^)]+\)\]',
            f'[![Douyin Likes](https://img.shields.io/badge/抖音获赞-{likes_str}-ff0050?style=flat&logo=tiktok&logoColor=white)]',
            content
        )
        content = re.sub(
            r'\[!\[Douyin Collects\]\(https://img\.shields\.io/badge/精准收藏-[^)]+\)\]',
            f'[![Douyin Collects](https://img.shields.io/badge/精准收藏-{collects_str}-f5a623?style=flat)]',
            content
        )
        content = re.sub(
            r'\[!\[Shares\]\(https://img\.shields\.io/badge/自发转发-[^)]+\)\]',
            f'[![Shares](https://img.shields.io/badge/自发转发-{shares_str}-1890ff?style=flat)]',
            content
        )

        # 正则替换正文中的粗体数字
        content = re.sub(
            r'斩获 \*\*[\d\.,\+kKwW]+ 点赞、[\d\.,\+kKwW]+ 精准高意向收藏与近 [\d\.,\+kKwW]+ 次自发转发\*\*',
            f'斩获 **{likes_str} 点赞、{collects_str} 精准高意向收藏与近 {shares_str} 次自发转发**',
            content
        )

        with open(README_CN, "w", encoding="utf-8") as f:
            f.write(content)
        print("[Success] README.md 更新完成")

    # 更新英文 README_EN.md
    if os.path.exists(README_EN):
        with open(README_EN, "r", encoding="utf-8") as f:
            content = f.read()

        content = re.sub(
            r'\[!\[Douyin Likes\]\(https://img\.shields\.io/badge/Douyin_Likes-[^)]+\)\]',
            f'[![Douyin Likes](https://img.shields.io/badge/Douyin_Likes-{likes_str}-ff0050?style=flat&logo=tiktok&logoColor=white)]',
            content
        )
        content = re.sub(
            r'\[!\[Douyin Bookmarks\]\(https://img\.shields\.io/badge/Bookmarks-[^)]+\)\]',
            f'[![Douyin Bookmarks](https://img.shields.io/badge/Bookmarks-{collects_str}-f5a623?style=flat)]',
            content
        )
        content = re.sub(
            r'\[!\[Shares\]\(https://img\.shields\.io/badge/Shares-[^)]+\)\]',
            f'[![Shares](https://img.shields.io/badge/Shares-{shares_str}-1890ff?style=flat)]',
            content
        )

        content = re.sub(
            r'generating \*\*[\d\.,\+kKwW]+ likes, [\d\.,\+kKwW]+ high-intent bookmarks, and ~[\d\.,\+kKwW]+ shares within 7 days\*\*',
            f'generating **{likes_str} likes, {collects_str} high-intent bookmarks, and ~{shares_str} shares within 7 days**',
            content
        )

        with open(README_EN, "w", encoding="utf-8") as f:
            f.write(content)
        print("[Success] README_EN.md 更新完成")

    # 保存历史统计数据
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"[Success] 数据已持久化保存至: {STATS_FILE}")


def main():
    parser = argparse.ArgumentParser(description="同步抖音视频指标到 README")
    parser.add_argument("--likes", type=int, help="手动指定点赞数")
    parser.add_argument("--collects", type=int, help="手动指定收藏数")
    parser.add_argument("--shares", type=int, help="手动指定分享/转发数")
    parser.add_argument("--auto", action="store_true", help="尝试通过 Playwright 自动抓取")

    args = parser.parse_args()

    stats = {}
    if args.likes is not None and args.collects is not None:
        stats = {
            "likes": args.likes,
            "collects": args.collects,
            "shares": args.shares or 1400,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    elif args.auto:
        stats = fetch_stats_via_playwright()
    else:
        # 默认模式：先尝试 auto，若失败且无历史则兜底使用最近已知数据
        stats = fetch_stats_via_playwright()
        if not stats:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    stats = json.load(f)
                print(f"[Info] 读取已有缓存数据: {stats}")
            else:
                stats = {
                    "likes": 8039,
                    "collects": 6081,
                    "shares": 1399,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

    if stats:
        update_readme_files(stats)
    else:
        print("[Failed] 未能获取有效数据，跳过文档更新")


if __name__ == "__main__":
    main()
