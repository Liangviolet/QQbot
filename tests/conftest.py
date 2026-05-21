"""pytest 共享配置 — 确保项目根目录在 sys.path 中"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保 `from src.xxx` 导入可用
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
