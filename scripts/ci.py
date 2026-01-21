#!/usr/bin/env python3
"""
GitHub Actions 辅助脚本

用于在GitHub Actions工作流中执行构建和处理任务。
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple
import fcntl
import time

from ci_utils import LyraVer, extract_vers_from_string

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.config import BuildConfig, ModCode
from lyra.config_loader import load_build_config
from lyra.builder import create_builder
from lyra.combo import CombinationCalculator, get_default_build_codes
from lyra.gen_page import DownloadPageConfig, DownloadPageGenerator, generate_download_page
from lyra.utils import (
    setup_logging, download_file, extract_zip, create_zip,
    copy_directory, safe_remove, run_command, find_game_file, apply_android_save_patch
)

logger = logging.getLogger(__name__)


class FileLock:
    """简单的文件锁实现，用于并发控制"""
    
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.lock_fd = None
    
    def __enter__(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock_fd = open(self.lock_file, 'w')
        # 获取排他锁
        fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_fd:
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
            self.lock_fd.close()


def build_single_task(task_args: Tuple) -> Tuple[str, str, bool, Optional[str]]:
    """
    单个构建任务（用于并行执行）
    
    Args:
        task_args: (pack_type, code, workspace, output_dir, date_param, dol_version, chs_version, verbose)
    
    Returns:
        (pack_type, code, success, error_msg)
    """
    pack_type, code, workspace, output_dir, date_param, dol_version, chs_version, verbose = task_args
    
    # 每个进程需要独立的logging配置
    setup_logging(verbose)
    
    # 加载配置
    from lyra.config_loader import load_build_config
    build_config = load_build_config()
    
    is_polyfill = code.startswith("polyfill-")
    suffix = "-polyfill" if is_polyfill else ""
    base_dir = workspace / build_config.base_dir
    workspace_inner = workspace / build_config.workspace_dir
    prepare_dir = workspace_inner / build_config.prepare_package_dir
    
    # 确定基包路径
    base_zip = base_dir / f"base{suffix}.zip"
    apk_dir = prepare_dir / f"apk{suffix}"
    
    # 构造build.py参数
    sys.argv = [
        'build.py',
        pack_type,
        code,
        '-o', str(output_dir),
    ]
    
    if date_param:
        sys.argv.insert(3, date_param)
    
    if verbose:
        sys.argv.append('-v')
    
    # 添加基包路径
    if pack_type == 'zip' and base_zip.exists():
        sys.argv.extend(['--base-zip', str(base_zip)])
    elif pack_type == 'apk' and apk_dir.exists():
        sys.argv.extend(['--base-apk-dir', str(apk_dir)])
    
    # 添加版本参数（如果指定了）
    if dol_version:
        sys.argv.extend(['--dol-version', dol_version])
    if chs_version:
        sys.argv.extend(['--chs-version', chs_version])
    
    # 执行构建
    try:
        from build import main as build_main
        result = build_main()
        if result == 0:
            return (pack_type, code, True, None)
        else:
            return (pack_type, code, False, f"构建返回非零退出码: {result}")
    except Exception as e:
        return (pack_type, code, False, str(e))


def cmd_build(args):
    """执行构建命令"""
    from build import main as build_main
    
    # 加载配置
    build_config = load_build_config()
    
    workspace = Path(args.workspace) if hasattr(args, 'workspace') else Path('.')
    base_dir = workspace / build_config.base_dir
    workspace_inner = workspace / build_config.workspace_dir
    prepare_dir = workspace_inner / build_config.prepare_package_dir
    
    # 判断是否为polyfill版本
    is_polyfill = args.mod_code.startswith("polyfill-")
    suffix = "-polyfill" if is_polyfill else ""
    
    # 构造参数并调用主构建脚本
    sys.argv = [
        'build.py',
        args.pack_type,
        args.mod_code,
    ]
    if args.date:
        sys.argv.append(args.date)
    if args.verbose:
        sys.argv.append('-v')
    
    # 添加基包路径参数（如果存在）
    base_zip = base_dir / f"base{suffix}.zip"
    base_apk = base_dir / f"base{suffix}.apk"
    apk_dir = prepare_dir / f"apk{suffix}"
    
    if args.pack_type == 'zip' and base_zip.exists():
        sys.argv.extend(['--base-zip', str(base_zip)])
    elif args.pack_type == 'apk':
        # 优先使用已解包目录（更快），否则使用apk基包
        if apk_dir.exists():
            sys.argv.extend(['--base-apk-dir', str(apk_dir)])
        elif base_apk.exists():
            sys.argv.extend(['--base-apk', str(base_apk)])
    
    return build_main()

def download_assets_from_chs_repo(workspace: Path, lyra_ver: Optional[LyraVer] = None) -> dict:
    """
    从汉化仓库下载必要的资源文件
    
    Args:
        workspace: 工作目录
        lyra_ver: 版本信息（可选，为None时使用latest release）
    
    Returns:
        下载文件的路径字典
    """
    import urllib.request
    
    chs_repo = "Eltirosto/Degrees-of-Lewdity-Chinese-Localization"
    
    # 确定要获取的release tag
    if lyra_ver:
        tag = f"v{lyra_ver.dol_ver}-chs-{lyra_ver.chs_ver}"
        api_url = f"https://api.github.com/repos/{chs_repo}/releases/tags/{tag}"
        logger.info(f"从指定tag下载: {tag}")
    else:
        api_url = f"https://api.github.com/repos/{chs_repo}/releases/latest"
        logger.info("从latest release下载")
    
    # 获取release信息
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            release_data = json.loads(response.read().decode())
    except Exception as e:
        logger.error(f"获取release信息失败: {e}")
        raise
    
    # 定义需要下载的文件模式（排除polyfill.APK）
    required_patterns = [
        ("apk", lambda name: name.endswith(".APK") and "polyfill" not in name.lower()),
        ("zip", lambda name: name.endswith(".zip") and "ModLoader" in name and "polyfill" not in name.lower()),
        ("polyfill_zip", lambda name: name.endswith(".zip") and "polyfill" in name.lower()),
        ("image_pack", lambda name: "GameOriginalImagePack" in name and name.endswith(".zip")),
        ("i18n", lambda name: "ModI18N" in name and name.endswith(".zip")),
    ]
    
    # 从release assets中筛选需要的文件
    assets_to_download = {}
    for asset in release_data.get('assets', []):
        name = asset['name']
        url = asset['browser_download_url']
        
        for key, matcher in required_patterns:
            if matcher(name) and key not in assets_to_download:
                assets_to_download[key] = {'name': name, 'url': url}
                break
    
    # 检查是否找到所有必需文件
    missing = [key for key, _ in required_patterns if key not in assets_to_download]
    if missing:
        logger.warning(f"未找到部分文件: {missing}")
    
    # 下载文件
    downloaded_files = {}
    for key, asset_info in assets_to_download.items():
        dest_path = workspace / asset_info['name']
        logger.info(f"下载 {key}: {asset_info['name']}")
        download_file(asset_info['url'], dest_path)
        downloaded_files[key] = dest_path
    
    return downloaded_files


def prepare_game_sources(workspace: Path, downloaded_files: dict, prepare_dir: Path) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """
    准备游戏源文件：解压并合并资源
    
    Args:
        workspace: 工作目录
        downloaded_files: 下载的文件路径字典
        prepare_dir: 准备目录
    
    Returns:
        (normal_zip_dir, polyfill_zip_dir, apk_extract_dir) 解压后的目录路径
    """
    normal_zip_dir = None
    polyfill_zip_dir = None
    apk_extract_dir = None
    
    # 解压GameOriginalImagePack获取img目录
    image_pack_dir = None
    if 'image_pack' in downloaded_files:
        image_pack_dir = prepare_dir / "image_pack_temp"
        if image_pack_dir.exists():
            safe_remove(image_pack_dir)
        extract_zip(downloaded_files['image_pack'], image_pack_dir)
        logger.info(f"已解压图片包到: {image_pack_dir}")
    
    # 解压普通版zip
    if 'zip' in downloaded_files:
        normal_zip_dir = prepare_dir / "zip"
        if normal_zip_dir.exists():
            safe_remove(normal_zip_dir)
        extract_zip(downloaded_files['zip'], normal_zip_dir)
        logger.info(f"已解压普通版zip到: {normal_zip_dir}")
        
        # 合并img
        if image_pack_dir:
            _merge_image_pack(image_pack_dir, normal_zip_dir)
    
    # 解压polyfill版zip
    if 'polyfill_zip' in downloaded_files:
        polyfill_zip_dir = prepare_dir / "zip-polyfill"
        if polyfill_zip_dir.exists():
            safe_remove(polyfill_zip_dir)
        extract_zip(downloaded_files['polyfill_zip'], polyfill_zip_dir)
        logger.info(f"已解压polyfill版zip到: {polyfill_zip_dir}")
        
        # 合并img
        if image_pack_dir:
            _merge_image_pack(image_pack_dir, polyfill_zip_dir)
    
    # 解压APK（使用apktool）
    if 'apk' in downloaded_files:
        apk_extract_dir = prepare_dir / "apk"
        # APK解压在后续流程中处理，这里只返回预期路径
    
    # 清理临时目录
    if image_pack_dir and image_pack_dir.exists():
        safe_remove(image_pack_dir)
    
    return normal_zip_dir, polyfill_zip_dir, apk_extract_dir


def _merge_image_pack(image_pack_dir: Path, target_dir: Path):
    """将图片包的img目录合并到目标目录"""
    # 查找img目录（可能在子目录中）
    img_src = None
    if (image_pack_dir / "img").exists():
        img_src = image_pack_dir / "img"
    else:
        # 搜索子目录
        for subdir in image_pack_dir.iterdir():
            if subdir.is_dir() and (subdir / "img").exists():
                img_src = subdir / "img"
                break
    
    if img_src:
        img_dst = target_dir / "img"
        copy_directory(img_src, img_dst)
        logger.debug(f"已合并图片包到: {img_dst}")
    else:
        logger.warning(f"在图片包中未找到img目录: {image_pack_dir}")


def download_extra_mods(workspace: Path) -> dict:
    """
    从额外的仓库下载mod文件
    
    Args:
        workspace: 工作目录
    
    Returns:
        下载的mod文件路径字典
    """
    import urllib.request
    
    extra_repos = [
        ("cheat", "DoL-Lyra/Cheat"),
        ("combat_status", "DoL-Lyra/CombatStatusDisplay"),
    ]
    
    downloaded_mods = {}
    
    for key, repo in extra_repos:
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        logger.info(f"从 {repo} 下载mod...")
        
        try:
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                release_data = json.loads(response.read().decode())
        except Exception as e:
            logger.error(f"获取 {repo} release信息失败: {e}")
            continue
        
        # 查找mod.zip文件
        for asset in release_data.get('assets', []):
            name = asset['name']
            if name.endswith('.mod.zip') or name == 'mod.zip':
                url = asset['browser_download_url']
                # 使用仓库名作为文件名前缀避免冲突
                dest_name = f"{repo.split('/')[1]}.mod.zip"
                dest_path = workspace / dest_name
                logger.info(f"下载 {key}: {name} -> {dest_name}")
                download_file(url, dest_path)
                downloaded_mods[key] = dest_path
                break
        else:
            logger.warning(f"在 {repo} 中未找到mod.zip文件")
    
    return downloaded_mods


def _add_mods_to_html(html_path: Path, mod_paths: list):
    """
    向HTML文件添加mod
    
    Args:
        html_path: HTML文件路径
        mod_paths: mod文件路径列表（按加载顺序）
    """
    from scripts.modmagic import add_mods_to_html
    
    # 过滤存在的mod文件
    existing_mods = [str(p) for p in mod_paths if p and p.exists()]
    
    if not existing_mods:
        logger.warning(f"没有可添加的mod文件")
        return
    
    logger.info(f"向 {html_path.name} 添加 {len(existing_mods)} 个mod...")
    add_mods_to_html(str(html_path), existing_mods, position="end")



def cmd_prepare_package(args):
    """
    准备游戏包（处理zip和apk）
    
    流程:
    1. 从汉化仓库下载源文件（zip、apk、polyfill、图片包、i18n）
    2. 解压并合并图片包
    3. 处理APK（反编译、修改配置）
    4. 生成基包
    
    输出结构:
    - workspace/base/base.zip, base-polyfill.zip  # ZIP基包
    - workspace/base/base.apk, base-polyfill.apk  # APK基包（已修改manifest和strings）
    - workspace/prepare_package/apk, apk-polyfill  # 已解包的APK目录（供后续复用）
    """
    setup_logging(args.verbose)
    
    lyra_ver = extract_vers_from_string(args.tag) if args.tag else None
    
    # 加载配置
    build_config = load_build_config()
    
    workspace = Path(args.workspace)
    base_dir = workspace / build_config.base_dir
    workspace_inner = workspace / build_config.workspace_dir
    prepare_dir = workspace_inner / build_config.prepare_package_dir
    
    base_dir.mkdir(parents=True, exist_ok=True)
    prepare_dir.mkdir(parents=True, exist_ok=True)
    
    # ========== 1. 下载源文件 ==========
    logger.info("========== 下载源文件 ==========")
    downloaded_files = download_assets_from_chs_repo(workspace, lyra_ver)
    
    if not downloaded_files:
        logger.error("未能下载任何文件")
        return 1
    
    # 下载额外的mod文件（Cheat, CombatStatusDisplay）
    extra_mods = download_extra_mods(workspace)
    
    # ========== 2. 解压并合并图片包 ==========
    logger.info("========== 解压源文件 ==========")
    normal_zip_dir, polyfill_zip_dir, _ = prepare_game_sources(
        workspace, downloaded_files, prepare_dir
    )
    
    # ========== 3. 下载apktool ==========
    apktool_url = "https://github.com/iBotPeaches/Apktool/releases/download/v2.12.0/apktool_2.12.0.jar"
    apktool_path = workspace / "apktool.jar"
    download_file(apktool_url, apktool_path)
    
    # ========== 4. 处理游戏包 ==========
    logger.info("========== 处理游戏包 ==========")
    
    # 获取APK文件
    apk_file = downloaded_files.get('apk')
    
    # 记录基包名称（用于后续构建）
    base_names = {}
    
    # 处理版本列表：(zip目录, 是否polyfill, 原始文件路径)
    versions_to_process = []
    if normal_zip_dir and normal_zip_dir.exists():
        versions_to_process.append((normal_zip_dir, False, downloaded_files.get('zip')))
    if polyfill_zip_dir and polyfill_zip_dir.exists():
        versions_to_process.append((polyfill_zip_dir, True, downloaded_files.get('polyfill_zip')))
    
    for zip_extract_dir, is_polyfill, source_file in versions_to_process:
        label = "polyfill" if is_polyfill else "normal"
        suffix = "-polyfill" if is_polyfill else ""
        logger.info(f"处理{label}版本")
        
        # 记录原始文件名（用于后续生成输出文件名）
        if source_file:
            base_names[label] = source_file.stem
        
        # 设置APK解包目录（每个版本独立）
        apk_extract_dir = prepare_dir / f"apk{suffix}"
        
        # 如果目录不存在且有APK，则解包
        if not apk_extract_dir.exists() and apk_file:
            logger.info(f"反编译APK到 {apk_extract_dir.name}...")
            run_command([
                "java", "-jar", str(apktool_path),
                "d", str(apk_file),
                "-o", str(apk_extract_dir)
            ])
            
            # 应用APK替换规则
            _apply_apk_replacements(apk_extract_dir, build_config)
        
        # ========== 5. 向HTML添加mod ==========
        # 按顺序添加: ModI18N, Cheat, CombatStatusDisplay
        mod_list = [
            downloaded_files.get('i18n'),
            extra_mods.get('cheat'),
            extra_mods.get('combat_status'),
        ]
        
        # 处理zip目录中的html
        zip_html = zip_extract_dir / "Degrees of Lewdity.html"
        if zip_html.exists():
            _add_mods_to_html(zip_html, mod_list)
        
        # 处理apk目录中的html
        if apk_extract_dir.exists():
            apk_html = apk_extract_dir / "assets" / "www" / "index.html"
            if apk_html.exists():
                _add_mods_to_html(apk_html, mod_list)

        
        # 输出ZIP基包到base目录
        output_zip = base_dir / f"base{suffix}.zip"
        create_zip(zip_extract_dir, output_zip)
        logger.info(f"ZIP基包已生成: {output_zip}")
        
        # 输出APK基包到base目录
        if apk_extract_dir.exists():
            output_apk = base_dir / f"base{suffix}.apk"
            run_command([
                "java", "-jar", str(apktool_path),
                "b", str(apk_extract_dir),
                "-o", str(output_apk)
            ])
            logger.info(f"APK基包已生成: {output_apk}")
        
        # 清理zip临时目录（保留apk解包目录供后续复用）
        safe_remove(zip_extract_dir)
    
    # 保存基包名称映射（供后续构建使用）
    if base_names:
        names_file = base_dir / "names.json"
        with open(names_file, 'w', encoding='utf-8') as f:
            json.dump(base_names, f, indent=2)
        logger.info(f"基包名称映射已保存: {names_file}")
    
    logger.info("========== 包处理完成 ==========")
    logger.info(f"  ZIP基包目录: {base_dir}")
    logger.info(f"  APK解包目录: {prepare_dir}")
    return 0


def _apply_apk_replacements(apk_extract_dir: Path, build_config: BuildConfig):
    """应用APK配置替换规则"""
    # 按文件分组替换规则
    file_replacements = {}
    for replacement in build_config.apk_replacements:
        if replacement.file not in file_replacements:
            file_replacements[replacement.file] = []
        file_replacements[replacement.file].append(replacement)
    
    # 应用替换规则
    for file_path, replacements in file_replacements.items():
        target_path = apk_extract_dir / file_path
        if target_path.exists():
            content = target_path.read_text(encoding='utf-8')
            for r in replacements:
                content = content.replace(r.pattern, r.replacement)
            target_path.write_text(content, encoding='utf-8')
            logger.debug(f"{file_path}已修改")


def cmd_build_all(args):
    """
    构建所有MOD组合包
    
    使用prepare-package生成的基包，批量构建所有组合。
    优先使用已解包的APK目录以提高速度。
    """
    setup_logging(args.verbose)
    
    # 加载配置
    build_config = load_build_config()
    
    workspace = Path(args.workspace)
    base_dir = workspace / build_config.base_dir
    workspace_inner = workspace / build_config.workspace_dir
    prepare_dir = workspace_inner / build_config.prepare_package_dir
    output_dir = workspace / build_config.output_dir
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查基包是否存在
    if not base_dir.exists():
        logger.error(f"基包目录不存在: {base_dir}")
        logger.error("请先运行 prepare-package 命令")
        return 1
    
    # 解析tag参数并提取版本信息和日期
    dol_version = None
    chs_version = None
    date_param = args.date
    
    if args.tag:
        # tag 格式: v0.5.7.9-5.0.2a-0112
        lyra_ver = extract_vers_from_string(args.tag)
        dol_version = lyra_ver.dol_ver
        chs_version = lyra_ver.chs_ver
        date_param = lyra_ver.date
        logger.info(f"从tag解析版本: DoL={dol_version}, Chs={chs_version}, Date={date_param}")
    
    # 获取所有构建代码
    calculator = CombinationCalculator()
    codes = calculator.get_build_codes(include_polyfill=True)
    codes = sorted(codes, key=lambda x: (x.startswith("polyfill-"), int(x.replace("polyfill-", "0"))))
    
    # 过滤包类型
    if args.pack_type:
        pack_types = [args.pack_type]
    else:
        pack_types = ['zip', 'apk']
    
    logger.info(f"开始批量构建 {len(codes)} 个组合，包类型: {pack_types}")
    
    success_count = 0
    fail_count = 0
    
    for pack_type in pack_types:
        for code in codes:
            is_polyfill = code.startswith("polyfill-")
            suffix = "-polyfill" if is_polyfill else ""
            
            # 确定基包路径
            base_zip = base_dir / f"base{suffix}.zip"
            apk_dir = prepare_dir / f"apk{suffix}"
            
            logger.info(f"\n{'='*50}")
            logger.info(f"构建: {pack_type} {code}")
            logger.info(f"{'='*50}")
            
            # 构造build.py参数
            sys.argv = [
                'build.py',
                pack_type,
                code,
                '-o', str(output_dir),
            ]
            
            if date_param:
                sys.argv.insert(3, date_param)
            
            if args.verbose:
                sys.argv.append('-v')
            
            # 添加基包路径
            if pack_type == 'zip' and base_zip.exists():
                sys.argv.extend(['--base-zip', str(base_zip)])
            elif pack_type == 'apk' and apk_dir.exists():
                sys.argv.extend(['--base-apk-dir', str(apk_dir)])
            
            # 添加版本参数（如果指定了）
            if dol_version:
                sys.argv.extend(['--dol-version', dol_version])
            if chs_version:
                sys.argv.extend(['--chs-version', chs_version])
            
            # 执行构建
            try:
                from build import main as build_main
                result = build_main()
                if result == 0:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"构建失败: {e}")
                fail_count += 1
    
    logger.info(f"\n{'='*50}")
    logger.info(f"批量构建完成: 成功 {success_count}, 失败 {fail_count}")
    logger.info(f"{'='*50}")
    
    return 0 if fail_count == 0 else 1


def cmd_build_all_parallel(args):
    """
    并行构建所有MOD组合包
    
    使用进程池并行执行构建任务，显著提升构建速度。
    自动处理并发问题：工作目录隔离、资源锁定、进程安全日志。
    """
    setup_logging(args.verbose)
    
    # 加载配置
    build_config = load_build_config()
    
    workspace = Path(args.workspace)
    base_dir = workspace / build_config.base_dir
    workspace_inner = workspace / build_config.workspace_dir
    prepare_dir = workspace_inner / build_config.prepare_package_dir
    output_dir = workspace / build_config.output_dir
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查基包是否存在
    if not base_dir.exists():
        logger.error(f"基包目录不存在: {base_dir}")
        logger.error("请先运行 prepare-package 命令")
        return 1
    
    # 解析tag参数并提取版本信息和日期
    dol_version = None
    chs_version = None
    date_param = args.date
    
    if args.tag:
        # tag 格式: v0.5.7.9-5.0.2a-0112
        tag_str = args.tag
        if tag_str.startswith('v'):
            tag_str = tag_str[1:]
        
        parts = tag_str.split('-')
        if len(parts) >= 3:
            dol_version = parts[0]  # 0.5.7.9
            chs_version = parts[1]  # 5.0.2a
            date_param = parts[2]   # 0112
            logger.info(f"从tag解析版本: DoL={dol_version}, Chs={chs_version}, Date={date_param}")
        else:
            logger.warning(f"tag格式不正确: {args.tag}，应为 v0.5.7.9-5.0.2a-0112")
    
    # 获取所有构建代码
    calculator = CombinationCalculator()
    codes = calculator.get_build_codes(include_polyfill=True)
    codes = sorted(codes, key=lambda x: (x.startswith("polyfill-"), int(x.replace("polyfill-", "0"))))
    
    # 过滤包类型
    if args.pack_type:
        pack_types = [args.pack_type]
    else:
        pack_types = ['zip', 'apk']
    
    # 构建任务列表
    tasks = []
    for pack_type in pack_types:
        for code in codes:
            tasks.append((
                pack_type,
                code,
                workspace,
                output_dir,
                date_param,
                dol_version,
                chs_version,
                args.verbose
            ))
    
    # 确定并发数
    max_workers = args.jobs if args.jobs else min(multiprocessing.cpu_count(), 4)
    
    logger.info(f"开始并行构建 {len(tasks)} 个任务，包类型: {pack_types}")
    logger.info(f"并发进程数: {max_workers}")
    logger.info(f"{'='*50}\n")
    
    success_count = 0
    fail_count = 0
    completed = 0
    
    # 使用进程池执行并行构建
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_task = {executor.submit(build_single_task, task): task for task in tasks}
        
        # 处理完成的任务
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            pack_type, code = task[0], task[1]
            completed += 1
            
            try:
                result_pack_type, result_code, success, error_msg = future.result()
                
                if success:
                    success_count += 1
                    logger.info(f"✓ [{completed}/{len(tasks)}] {result_pack_type} {result_code} - 成功")
                else:
                    fail_count += 1
                    logger.error(f"✗ [{completed}/{len(tasks)}] {result_pack_type} {result_code} - 失败: {error_msg}")
            except Exception as e:
                fail_count += 1
                logger.error(f"✗ [{completed}/{len(tasks)}] {pack_type} {code} - 异常: {e}")
    
    logger.info(f"\n{'='*50}")
    logger.info(f"并行构建完成: 成功 {success_count}, 失败 {fail_count}")
    logger.info(f"{'='*50}")
    
    return 0 if fail_count == 0 else 1


def cmd_generate_matrix(args):
    """生成构建矩阵（用于GitHub Actions）"""
    # 使用组合计算器生成代码列表
    calculator = CombinationCalculator()
    codes = calculator.get_build_codes(include_polyfill=True)

    codes = sorted(codes, key=lambda x: (x.startswith("polyfill-"), int(x.replace("polyfill-","0"))))
    
    # 输出为GitHub Actions格式
    if args.output_format == 'shell':
        # 输出空格分隔的代码列表，用于 shell 脚本
        print(' '.join(codes))
    else:
        # JSON 格式（默认）
        print(json.dumps(codes, indent=2))
    
    return 0


def cmd_generate_page(args):
    """生成下载页面"""
    setup_logging(args.verbose)
    
    output_path = Path(args.output) if args.output else None
    
    content = generate_download_page(
        version=args.version,
        output_path=output_path,
        github_owner=args.github_owner,
        github_repo=args.github_repo,
    )
    
    if not output_path:
        print(content)
    else:
        logger.info(f"下载页面已生成: {output_path}")
    
    return 0


def cmd_list_combinations(args):
    """列出所有MOD组合"""
    calculator = CombinationCalculator()
    print(calculator.to_string())
    return 0


def cmd_check_update(args):
    """检查是否需要更新"""
    import urllib.request
    
    # 获取汉化仓库最新release
    url = "https://api.github.com/repos/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/releases/latest"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            origin_tag = data['tag_name']
    except Exception as e:
        logger.error(f"获取汉化仓库版本失败: {e}")
        return 1
    
    # 解析版本号
    # 格式: DoL-ModLoader-X.X.X-chs-X.X.X
    chs_ver = origin_tag.split('-')[2] if '-' in origin_tag else origin_tag
    
    # 获取本仓库最新tag
    try:
        result = run_command(
            ['git', 'tag', '--sort=-v:refname'],
            capture_output=True
        )
        tags = result.stdout.strip().split('\n')
        latest_tag = tags[0] if tags else ""
        mods_ver = latest_tag.split('-')[1] if '-' in latest_tag else ""
    except Exception as e:
        logger.error(f"获取本仓库版本失败: {e}")
        mods_ver = ""
    
    need_update = chs_ver != mods_ver
    
    # 输出结果
    result = {
        'need_update': need_update,
        'origin_tag': origin_tag,
        'chs_ver': chs_ver,
        'mods_ver': mods_ver,
    }
    
    if need_update:
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=8))
        date_str = datetime.now(tz).strftime("%m%d")
        new_tag = f"{origin_tag.replace('chs-', '')}-{date_str}"
        result['new_tag'] = new_tag
    
    if args.github_output:
        # 写入GitHub Actions输出
        with open(args.github_output, 'a') as f:
            for key, value in result.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                f.write(f"{key}={value}\n")
    else:
        print(json.dumps(result, indent=2))
    
    return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="GitHub Actions 辅助脚本"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # build 命令
    build_parser = subparsers.add_parser('build', help='构建整合包')
    build_parser.add_argument('pack_type', choices=['zip', 'apk'])
    build_parser.add_argument('mod_code')
    build_parser.add_argument('date', nargs='?')
    build_parser.add_argument('--workspace', default='.')
    build_parser.add_argument('-v', '--verbose', action='store_true')
    
    # prepare-package 命令
    prep_parser = subparsers.add_parser('prepare-package', help='准备游戏包')
    prep_parser.add_argument('--workspace', default='.')
    prep_parser.add_argument('--tag', help='tag参数（格式如 v0.5.7.9-5.0.2a-0112，用于指定版本和日期）')
    prep_parser.add_argument('-v', '--verbose', action='store_true')
    
    # build-all 命令
    build_all_parser = subparsers.add_parser('build-all', help='批量构建所有组合')
    build_all_parser.add_argument('pack_type', nargs='?', choices=['zip', 'apk'], help='包类型（可选，默认构建两种）')
    build_all_parser.add_argument('date', nargs='?', help='日期参数')
    build_all_parser.add_argument('--tag', help='tag参数（格式如 v0.5.7.9-5.0.2a-0112，用于指定版本和日期）')
    build_all_parser.add_argument('--workspace', default='.')
    build_all_parser.add_argument('-v', '--verbose', action='store_true')
    
    # build-all-parallel 命令
    build_all_parallel_parser = subparsers.add_parser('build-all-parallel', help='并行批量构建所有组合')
    build_all_parallel_parser.add_argument('pack_type', nargs='?', choices=['zip', 'apk'], help='包类型（可选，默认构建两种）')
    build_all_parallel_parser.add_argument('date', nargs='?', help='日期参数')
    build_all_parallel_parser.add_argument('--tag', help='tag参数（格式如 v0.5.7.9-5.0.2a-0112，用于指定版本和日期）')
    build_all_parallel_parser.add_argument('--jobs', '-j', type=int, help='并发进程数（默认为CPU核心数或4，取较小值）')
    build_all_parallel_parser.add_argument('--workspace', default='.')
    build_all_parallel_parser.add_argument('-v', '--verbose', action='store_true')
    
    # prepare-pwa 命令
    pwa_parser = subparsers.add_parser('prepare-pwa', help='准备PWA文件')
    pwa_parser.add_argument('--source', required=True)
    pwa_parser.add_argument('--output', required=True)
    pwa_parser.add_argument('--template', required=True)
    pwa_parser.add_argument('--repo-name')
    pwa_parser.add_argument('-v', '--verbose', action='store_true')
    
    # generate-matrix 命令
    matrix_parser = subparsers.add_parser('generate-matrix', help='生成构建矩阵')
    matrix_parser.add_argument('--output-format', choices=['github', 'json', 'shell'], default='json')
    
    # generate-page 命令
    page_parser = subparsers.add_parser('generate-page', help='生成下载页面')
    page_parser.add_argument('--version', required=True, help='版本号')
    page_parser.add_argument('--output', help='输出文件路径')
    page_parser.add_argument('--github-owner', default='sakarie9', help='GitHub用户名')
    page_parser.add_argument('--github-repo', default='DoL-Lyra', help='GitHub仓库名')
    page_parser.add_argument('-v', '--verbose', action='store_true')
    
    # list-combinations 命令
    list_parser = subparsers.add_parser('list-combinations', help='列出所有MOD组合')
    
    # check-update 命令
    update_parser = subparsers.add_parser('check-update', help='检查更新')
    update_parser.add_argument('--github-output', help='GitHub Actions输出文件')
    update_parser.add_argument('-v', '--verbose', action='store_true')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    commands = {
        'build': cmd_build,
        'build-all': cmd_build_all,
        'build-all-parallel': cmd_build_all_parallel,
        'prepare-package': cmd_prepare_package,
        'generate-matrix': cmd_generate_matrix,
        'generate-page': cmd_generate_page,
        'list-combinations': cmd_list_combinations,
        'check-update': cmd_check_update,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
