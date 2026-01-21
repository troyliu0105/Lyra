"""
DoL-Lyra CLI 入口

允许通过 python -m lyra 运行。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import main

if __name__ == "__main__":
    sys.exit(main())
