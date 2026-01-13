#!/usr/bin/env python3
"""
DoL-Lyra 整合包构建工具

命令行入口脚本。
"""

import argparse
import logging
import sys
from pathlib import Path

from lyra import __version__
from lyra.config import BuildConfig, ModCode
from lyra.builder import create_builder
from lyra.combo import CombinationCalculator, get_default_build_codes
from lyra.gen_page import generate_download_page
from lyra.utils import setup_logging, find_game_file

logger = logging.getLogger(__name__)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="DoL-Lyra 整合包构建工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 构建ZIP包，MOD代码为3
  python build.py zip 3
  
  # 构建APK包，包含BESC和作弊
  python build.py apk 3 --date 0113
  
  # 构建polyfill版本
  python build.py zip polyfill-3
  
  # 批量构建所有组合
  python build.py zip all
  
  # 列出所有可用组合
  python build.py --list-combinations
  
  # 生成下载页面
  python build.py --generate-page v1.0.0
  
  # 使用verbose模式
  python build.py zip 3 -v

MOD代码说明:
  1    - BESC (BEEESSS社区精灵合集)
  2    - 作弊功能
  4    - CSD
  8    - BJ特写
  16   - KR特写
  32   - Hikari特写
  64   - WAX美化
  128  - Susato模型
  256  - UCB (通用战斗美化)
  512  - Goose特写
  1024 - AU女性
  2048 - AU男性
  4096 - AU双性
  
组合示例:
  3    = BESC + 作弊
  35   = BESC + 作弊 + Hikari
  259  = BESC + 作弊 + UCB
  all  = 构建所有计算出的有效组合
"""
    )
    
    parser.add_argument(
        'pack_type',
        nargs='?',
        choices=['zip', 'apk'],
        help='包类型: zip 或 apk'
    )
    
    parser.add_argument(
        'mod_code',
        nargs='?',
        help='MOD代码，可以是数字、"polyfill-数字" 或 "all"'
    )
    
    parser.add_argument(
        'date',
        nargs='?',
        default=None,
        help='日期参数，格式为MMDD（如0113）或tag名（如v0.4.5.3-alpha1.6.0-0216）'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=Path('output'),
        help='输出目录 (默认: output)'
    )
    
    parser.add_argument(
        '-s', '--source',
        type=Path,
        default=None,
        help='源文件路径 (默认: 自动查找)'
    )
    
    parser.add_argument(
        '--list-combinations',
        action='store_true',
        help='列出所有可用的MOD组合'
    )
    
    parser.add_argument(
        '--generate-page',
        metavar='VERSION',
        help='生成指定版本的下载页面'
    )
    
    parser.add_argument(
        '--base-zip',
        type=Path,
        default=None,
        help='预处理的ZIP基包路径（CI模式）'
    )
    
    parser.add_argument(
        '--base-apk',
        type=Path,
        default=None,
        help='预处理的APK基包路径（需要解包）'
    )
    
    parser.add_argument(
        '--base-apk-dir',
        type=Path,
        default=None,
        help='已解包的APK目录路径（不需要解包，直接复制）'
    )
    
    parser.add_argument(
        '--dol-version',
        default=None,
        help='DoL版本号（CI模式，用于覆盖从源文件解析的版本）'
    )
    
    parser.add_argument(
        '--chs-version',
        default=None,
        help='汉化版本号（CI模式，用于覆盖从源文件解析的版本）'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    return parser.parse_args()


def build_single(pack_type: str, mod_code_str: str, date_param: str, 
                 output_dir: Path, source_file: Path = None,
                 base_zip: Path = None, base_apk: Path = None,
                 base_apk_dir: Path = None, dol_version: str = None,
                 chs_version: str = None) -> int:
    """构建单个包
    
    Args:
        pack_type: 包类型 (zip/apk)
        mod_code_str: MOD代码字符串
        date_param: 日期参数
        output_dir: 输出目录
        source_file: 源文件路径（独立运行时使用）
        base_zip: 预处理的ZIP基包路径（CI模式）
        base_apk: 预处理的APK基包路径（需要解包）
        base_apk_dir: 已解包的APK目录路径（不需要解包）
    """
    # 解析MOD代码
    is_polyfill = False
    
    if mod_code_str.startswith("polyfill-"):
        is_polyfill = True
        mod_code_str = mod_code_str.split("-")[1]
        logger.info("使用polyfill版本")
    
    try:
        mod_code = int(mod_code_str)
    except ValueError:
        logger.error(f"无效的MOD代码: {mod_code_str}")
        return 1
    
    # 创建配置
    config = BuildConfig(
        pack_type=pack_type,
        mod_code=mod_code,
        date_param=date_param,
        is_polyfill=is_polyfill,
        output_dir=output_dir,
        base_zip_path=base_zip,
        base_apk_path=base_apk,
        base_apk_dir=base_apk_dir,
        dol_version=dol_version,
        chs_version=chs_version,
    )
    
    # 查找源文件（仅在无基包时需要）
    has_base_package = (base_zip and base_zip.exists()) or \
                       (base_apk and base_apk.exists()) or \
                       (base_apk_dir and base_apk_dir.exists())
    
    if not has_base_package:
        if not source_file:
            source_file = find_game_file(Path('.'), include_polyfill=is_polyfill)
        
        if not source_file or not source_file.exists():
            logger.error("未找到游戏文件")
            return 1
        
        logger.info(f"源文件: {source_file}")
    else:
        # 使用基包时，source_file可以是占位符
        if not source_file:
            source_file = base_zip or base_apk or Path("placeholder")
        logger.info("使用预处理基包模式")
    
    # 创建构建器并执行构建
    builder = create_builder(config)
    result = builder.build(source_file)
    
    if result.success:
        logger.info(f"✓ 构建成功: {result.output_name}")
        logger.info(f"  输出路径: {result.output_path}")
        if result.applied_mods:
            logger.info(f"  应用的MOD: {', '.join(result.applied_mods)}")
        return 0
    else:
        logger.error(f"✗ 构建失败: {result.error}")
        return 1


def build_all(pack_type: str, date_param: str, output_dir: Path, 
              source_file: Path = None) -> int:
    """批量构建所有组合"""
    codes = get_default_build_codes()
    
    logger.info(f"开始批量构建 {len(codes)} 个组合...")
    
    success_count = 0
    fail_count = 0
    
    for code in codes:
        logger.info(f"\n{'='*50}")
        logger.info(f"正在构建: {pack_type} {code}")
        logger.info(f"{'='*50}")
        
        result = build_single(pack_type, code, date_param, output_dir, source_file)
        
        if result == 0:
            success_count += 1
        else:
            fail_count += 1
    
    logger.info(f"\n{'='*50}")
    logger.info(f"批量构建完成: 成功 {success_count}, 失败 {fail_count}")
    logger.info(f"{'='*50}")
    
    return 0 if fail_count == 0 else 1


def main():
    """主入口函数"""
    args = parse_args()
    
    # 设置日志
    setup_logging(args.verbose)
    
    # 处理 --list-combinations
    if args.list_combinations:
        calculator = CombinationCalculator()
        print(calculator.to_string())
        return 0
    
    # 处理 --generate-page
    if args.generate_page:
        content = generate_download_page(args.generate_page)
        print(content)
        return 0
    
    # 如果没有指定pack_type或mod_code，显示帮助
    if not args.pack_type or not args.mod_code:
        print("错误: 需要指定 pack_type 和 mod_code")
        print("使用 --help 查看帮助")
        return 1
    
    # logger.info(f"DoL-Lyra 构建工具 v{__version__}")
    logger.info(f"包类型: {args.pack_type}, MOD代码: {args.mod_code}")
    
    # 批量构建
    if args.mod_code == "all":
        return build_all(
            args.pack_type,
            args.date,
            args.output,
            args.source,
        )
    
    # 单个构建
    return build_single(
        args.pack_type,
        args.mod_code,
        args.date,
        args.output,
        args.source,
        base_zip=args.base_zip,
        base_apk=args.base_apk,
        base_apk_dir=args.base_apk_dir,
        dol_version=args.dol_version,
        chs_version=args.chs_version,
    )


if __name__ == "__main__":
    sys.exit(main())
