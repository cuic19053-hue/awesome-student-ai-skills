#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_writing_style.py — 向 35 个子 skill 批量注入「去 AI 味」写作规范引用块。

背景
----
用户反馈「AI 味太浓」。根因之一是每个子 skill 各自零散地写文风条款，
既不一致也不可执行。本脚本把 `docs/design/WRITING_STYLE.md` 的压缩版
注入到每个 `subskills/<id>/SKILL.md` 的「质检清单」章节**之前**，
保证模型在写正文前先读到硬约束。

设计要点
--------
- 幂等：靠 `<!-- WRITING-STYLE:START -->` / `<!-- WRITING-STYLE:END -->`
  标记识别，重复运行只替换块内容，不会重复插入。
- 锚点容错：35 份文件的质检章节标题写法不一（`## 十三、质检清单`、
  `## §13 build.py 接口 + 质检清单…`），用正则匹配含「质检清单」的 H2。
- 无锚点兜底：找不到质检章节时追加到文末，并记录 warning。
- 只改 SKILL.md，不碰 build.py；不触碰 README 的 KB 门禁口径。

用法
----
    python3 scripts/inject_writing_style.py --dry-run   # 预览
    python3 scripts/inject_writing_style.py             # 执行
    python3 scripts/inject_writing_style.py --check     # 校验（CI 用，未注入则非零退出）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SUBSKILLS = ROOT / "subskills"
STYLE_DOC = ROOT / "docs" / "design" / "WRITING_STYLE.md"

START_MARK = "<!-- WRITING-STYLE:START -->"
END_MARK = "<!-- WRITING-STYLE:END -->"

# 含「质检清单」的 H2 标题（兼容 `## 十三、质检清单` / `## §13 …质检清单…`）
ANCHOR_RE = re.compile(r"^##\s.*质检清单.*$", re.M)
BLOCK_RE = re.compile(
    re.escape(START_MARK) + r".*?" + re.escape(END_MARK) + r"\n*",
    re.S,
)

BLOCK = f"""{START_MARK}
## 写作风格硬约束（去 AI 味 · 强制）

> 完整规范见 [`docs/design/WRITING_STYLE.md`](../../docs/design/WRITING_STYLE.md)。
> 本节是压缩版，**撰写正文前必读，交付前必须过检测**。

### 一条总原则

**每个句子都必须能落到具体的人、事、时间、数字或对象上；落不到的句子，删掉。**
自检方法：读完一句问「这句能换成别人吗？」——能换，就是套话。

### 六条硬约束（及格线 75/100）

| # | 约束 | 量化判据 |
|---|---|---|
| 1 | 不写空话套话 | 每千字命中套话 ≤3 次 |
| 2 | 不用排比对仗 | 同构句连续 ≤2 句 |
| 3 | 不堆抽象大词 | 每千字抽象词 ≤4 次 |
| 4 | 必须具体 | 每千字数字/专名 ≥8 处 |
| 5 | 句长要参差 | 句长变异系数 ≥0.35 |
| 6 | 不用模板开头 | 禁止「时光荏苒」「本人自入学以来」 |

### 高频禁用词（出现即改）

具有重要意义、具有重大意义、意义重大、影响深远、作用显著、效果显著、成效显著、
成绩斐然、成果丰硕、高度重视、切实增强、切实提升、不断提升、持续提升、
进一步加强、进一步完善、进一步深化、不断深化、深入推进、全面推进、扎实开展、
稳步推进、着力打造、全力推动、取得显著成效、获得一致好评、受到广泛好评、
得到充分肯定、获得高度评价、与此同时、在此基础上、综上所述、总而言之、
值得一提的是、不难看出、由此可见、众所周知、不懈努力、刻苦钻研、勤奋刻苦、
锐意进取、开拓创新、勇于探索、敢于突破、迈上新台阶、开创新局面、谱写新篇章、
踏上新征程、展现新作为、彰显新担当、焕发新气象、贡献青春力量、绽放青春光彩、
书写青春华章、以青春之我、坚定理想信念、厚植家国情怀、锤炼过硬本领、砥砺意志品质、
综合素质突出、全面发展、品学兼优、德智体美劳、起到了模范带头作用、
发挥了示范引领作用、树立了良好榜样、得到了师生的一致认可、深受老师和同学的好评、
为集体作出了积极贡献、为团队贡献了自己的力量、奠定了坚实的基础、
打下了坚实的基础、提供了有力支撑、注入了强劲动力、开辟了新的途径、探索了新的模式

抽象大词（无具体指涉时禁用）：格局、境界、高度、深度、广度、维度、层面、体系、
机制、路径、抓手、载体、平台、生态、闭环、赋能、助力、引领、驱动、融合、协同、
联动、统筹、底层逻辑、顶层设计、系统性思维、全局视野、战略高度、核心素养、
综合能力、内生动力、长效机制

### 替换动作（照做即可）

| 原写法 | 改写成 |
|---|---|
| 学习成绩优异，名列前茅 | 专业 3/127，加权 91.4，`<课程名>` 98 分 |
| 积极参加学科竞赛 | 2024 年 11 月 `<赛事全名>` 省赛二等奖，作品 `<名称>`，我负责 `<模块>` |
| 在导师指导下参与科研 | 参与 `<导师>` 的 `<课题名>`，负责 `<具体工作>`，产出 `<论文/专利/数据>` |
| 具有较强的团队协作能力 | 删掉。改为：`<时间>` 带 `<人数>` 人完成 `<任务>`，遇到 `<冲突>`，怎么解决 |
| 思想上积极向党组织靠拢 | `<年/月>` 提交入党申请书，`<年/月>` 成为积极分子，参加 `<次数>` 次党课 |
| 热心公益，积极参加志愿服务 | `<机构>` 志愿服务 `<小时>` 小时，服务 `<对象>` `<人数>` 人 |

### 句式要求

1. **长短句交替**：每 3~5 句里至少有一句 ≤12 字或 ≥60 字。
2. **一段一个事实**：段首句不要用「在……方面」。
3. **少用第一人称抒情**：「我深深感到」「我深刻认识到」一律删除。
4. **数字优先**：能用数字就不用形容词。「多次」→「7 次」，「大量」→「4200 张」。
5. 不用破折号堆叠解释，不连续套用「不仅……而且……」。

### 交付前强制质检（任一项不过 → 不允许交付）

```bash
# 1) AI 味检测（及格线 75）
python3 utils/ai_flavor_check.py --file draft.txt --min-score 75

# 2) 查重预检（阈值 30%）
python3 utils/plagiarism_checker.py --file draft.txt --skill <skill_name>

# 3) 评审模拟（含文风维度）
python3 utils/review_simulator.py --skill <skill_name> --file draft.txt
```

### 冲突处理

政策条文、领导讲话、文件原名**允许庄重书面语**，不算套话。
检测时加 `--allow-policy-quotes`（该维度扣分减半）。
但引用必须写成 `《文件全名》（发文号）`，且只引与论点直接相关的 1~2 句。

### 反模式

- ❌ 把子 skill 里的「金句模板」当范文直接套用
- ❌ 用排比段凑字数
- ❌ 通篇无一个数字、无一个专有名词
- ❌ 检测得分 <75 仍交付
- ❌ 只删套话不补事实（删完变空段落，同样不及格）

{END_MARK}
"""


def _iter_skill_files() -> List[Path]:
    return sorted(SUBSKILLS.glob("*/SKILL.md"))


def _build_new_content(original: str) -> Tuple[str, str]:
    """返回 (新内容, 处理方式)。处理方式用于日志。"""
    # 已有标记 → 原地替换（BLOCK 自带尾部换行，正则已吞掉多余空行）
    if BLOCK_RE.search(original):
        return BLOCK_RE.sub(BLOCK, original, count=1), "replaced"

    # 找质检清单章节（BLOCK 自带尾部换行，直接拼接即可与 replaced 路径收敛）
    m = ANCHOR_RE.search(original)
    if m:
        idx = m.start()
        head, tail = original[:idx], original[idx:]
        return f"{head}{BLOCK}{tail}", "inserted-before-qa"

    # 兜底：追加到文末
    sep = "" if original.endswith("\n") else "\n"
    return f"{original}{sep}\n{BLOCK}", "appended"


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="向 35 个子 skill 注入去 AI 味写作规范")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写盘")
    ap.add_argument("--check", action="store_true", help="校验模式：有文件未注入则退出码 1")
    args = ap.parse_args(argv)

    if not STYLE_DOC.exists():
        print(f"❌ 规范文件缺失：{STYLE_DOC}")
        return 2

    files = _iter_skill_files()
    if not files:
        print("❌ 未找到任何 subskills/*/SKILL.md")
        return 2

    changed: List[Tuple[str, str]] = []
    missing: List[str] = []

    for path in files:
        name = path.parent.name
        original = path.read_text(encoding="utf-8")
        new_content, how = _build_new_content(original)
        if how == "appended":
            missing.append(name)
        if new_content != original:
            changed.append((name, how))
            if not args.dry_run and not args.check:
                path.write_text(new_content, encoding="utf-8")

    if args.check:
        if changed:
            print(f"❌ {len(changed)} 个子 skill 的写作规范块缺失或过期：")
            for name, how in changed[:40]:
                print(f"   - {name} ({how})")
            print("\n请运行：python3 scripts/inject_writing_style.py")
            return 1
        print(f"✅ 全部 {len(files)} 个子 skill 已注入最新写作规范")
        return 0

    verb = "将修改" if args.dry_run else "已修改"
    print(f"{verb} {len(changed)}/{len(files)} 个文件")
    for name, how in changed:
        print(f"  - {name}: {how}")
    if missing:
        print(f"\n⚠️  {len(missing)} 个文件未找到「质检清单」章节，已追加到文末：")
        for name in missing:
            print(f"   - {name}")
    if args.dry_run:
        print("\n（--dry-run，未写盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
