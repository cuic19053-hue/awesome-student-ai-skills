#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
debug_demo.py - 你的第一个断点调试实战入口
运行方式：在 Antigravity IDE 中打开此文件，点击右上角 "Debug Python File"（或按 F5）
"""

from utils.dispatcher import Dispatcher

def main():
    print("====== 1. 初始化 35 赛道分流器 ======")
    dispatcher = Dispatcher()

    user_query = "我要写大创申报书"
    print(f"====== 2. 模拟用户输入: '{user_query}' ======")

    # 这一行会调用 utils/dispatcher.py 里的 dispatch 函数
    matches = dispatcher.dispatch(user_query, top_n=3)

    print("====== 3. 匹配结果 ======")
    for rank, item in enumerate(matches, 1):
        print(f"第 {rank} 名: {item['display_name']} ({item['name']}) -> 得分: {item['score']}分, 命中理由: {item['matched']}")

if __name__ == "__main__":
    main()
