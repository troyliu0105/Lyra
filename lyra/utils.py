"""
工具函数模块

提供文件操作、下载、压缩等通用功能。
"""

import hashlib
import logging
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """配置日志系统"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def download_file(url: str, dest: Path, quiet: bool = False) -> Path:
    """
    下载文件到指定路径
    
    Args:
        url: 下载URL
        dest: 目标路径
        quiet: 是否静默模式
        
    Returns:
        下载的文件路径
    """
    if dest.exists():
        logger.debug(f"文件已存在，跳过下载: {dest}")
        return dest
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"下载: {url}")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest, 'wb') as f:
        if quiet or total_size == 0:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        else:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=dest.name) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
    
    return dest


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """
    解压ZIP文件
    
    Args:
        zip_path: ZIP文件路径
        dest_dir: 目标目录
        
    Returns:
        解压目录
    """
    logger.info(f"解压ZIP: {zip_path} -> {dest_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)
    
    return dest_dir


def create_zip(source_dir: Path, dest_path: Path) -> Path:
    """
    创建ZIP压缩包
    
    Args:
        source_dir: 源目录
        dest_path: 目标ZIP文件路径
        
    Returns:
        ZIP文件路径
    """
    logger.info(f"创建ZIP: {source_dir} -> {dest_path}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                arc_name = file_path.relative_to(source_dir)
                zf.write(file_path, arc_name)
    
    return dest_path


def extract_tar_gz(tar_path: Path, dest_dir: Path, strip_components: int = 0) -> Path:
    """
    解压tar.gz文件
    
    Args:
        tar_path: tar.gz文件路径
        dest_dir: 目标目录
        strip_components: 跳过的目录层级数
        
    Returns:
        解压目录
    """
    logger.info(f"解压tar.gz: {tar_path} -> {dest_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    with tarfile.open(tar_path, 'r:gz') as tf:
        for member in tf.getmembers():
            if strip_components > 0:
                # 移除前N个路径组件
                parts = Path(member.name).parts
                if len(parts) <= strip_components:
                    continue
                member.name = str(Path(*parts[strip_components:]))
            
            tf.extract(member, dest_dir)
    
    return dest_dir


def copy_directory(src: Path, dest: Path, overwrite: bool = True):
    """
    复制目录内容
    
    Args:
        src: 源目录
        dest: 目标目录
        overwrite: 是否覆盖已存在的文件
    """
    logger.debug(f"复制目录: {src} -> {dest}")
    
    for item in src.rglob('*'):
        if item.is_file():
            rel_path = item.relative_to(src)
            dest_path = dest / rel_path
            
            if dest_path.exists() and not overwrite:
                continue
            
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest_path)


def safe_move(src: Path, dest: Path) -> bool:
    """
    安全移动文件（处理文件名大小写问题）
    
    Args:
        src: 源路径
        dest: 目标路径
        
    Returns:
        是否成功
    """
    try:
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            return True
    except Exception as e:
        logger.warning(f"移动文件失败 {src} -> {dest}: {e}")
    return False


def safe_remove(path: Path) -> bool:
    """
    安全删除文件或目录
    
    Args:
        path: 要删除的路径
        
    Returns:
        是否成功
    """
    try:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
    except Exception as e:
        logger.warning(f"删除失败 {path}: {e}")
    return False


def run_command(
    cmd: list[str],
    cwd: Optional[Path] = None,
    capture_output: bool = False,
    check: bool = True
) -> subprocess.CompletedProcess:
    """
    运行外部命令
    
    Args:
        cmd: 命令及参数列表
        cwd: 工作目录
        capture_output: 是否捕获输出
        check: 是否检查返回码
        
    Returns:
        CompletedProcess对象
    """
    logger.debug(f"运行命令: {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        check=check,
        text=True
    )


def find_game_file(directory: Path, include_polyfill: bool = False) -> Optional[Path]:
    """
    查找游戏文件
    
    Args:
        directory: 搜索目录
        include_polyfill: 是否查找polyfill版本
        
    Returns:
        找到的文件路径，未找到返回None
    """
    for f in directory.iterdir():
        if f.is_file() and f.name.startswith("DoL"):
            has_polyfill = "polyfill" in f.name
            if include_polyfill == has_polyfill:
                return f
    return None


def get_file_hash(path: Path, algorithm: str = 'md5') -> str:
    """
    计算文件哈希值
    
    Args:
        path: 文件路径
        algorithm: 哈希算法 (md5, sha256等)
        
    Returns:
        哈希值字符串
    """
    hasher = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_version_from_filename(filename: str) -> tuple[str, str]:
    """
    从文件名解析版本号
    
    Args:
        filename: 文件名，如 "DoL-ModLoader-1.2.3-chs-4.5.6.zip"
        
    Returns:
        (dol_version, chs_version) 元组
    """
    basename = Path(filename).stem
    parts = basename.split('-')
    
    # 尝试提取版本号
    dol_ver = ""
    chs_ver = ""
    
    for i, part in enumerate(parts):
        if part.startswith('v') or part[0].isdigit():
            if not dol_ver:
                dol_ver = part
            elif not chs_ver:
                chs_ver = part
    
    return dol_ver, chs_ver

def apply_android_save_patch(html_path: Path) -> bool:
        """
        应用Android保存补丁
        
        Args:
            html_path: HTML文件路径
            
        Returns:
            是否成功
        """
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 添加Cordova脚本
            title_tag = '<title>Degrees of Lewdity</title>'
            insert_pos = content.find(title_tag)
            if insert_pos != -1:
                insert_pos += len(title_tag)
                cordova_scripts = '''
<script src="cordova.js" type="text/javascript"></script>
<script src="custom_cordova_additions.js" type="text/javascript"></script>'''
                content = content[:insert_pos] + cordova_scripts + content[insert_pos:]
            
            # 替换保存函数
            content = content.replace('saveAs(', 'cordova.plugins.saveDialog.saveFile(')
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Android保存补丁已应用: {html_path}")
            return True
            
        except Exception as e:
            logger.error(f"应用Android保存补丁失败: {e}")
            return False