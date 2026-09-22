# -*- coding: utf-8 -*-
"""pytest 公共配置：把仓库根目录加入 sys.path，便于 import scripts/ 与 server/。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
