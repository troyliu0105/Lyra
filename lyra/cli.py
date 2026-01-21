"""
CLI入口模块

提供命令行接口的入口点。
"""

import sys


def main():
    """CLI主入口"""
    # 导入并运行主构建脚本
    from build import main as build_main

    return build_main()


if __name__ == "__main__":
    sys.exit(main())
