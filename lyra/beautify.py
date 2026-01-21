"""
美化处理模块

处理各种美化MOD的下载和安装。
"""

import logging
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import ModCode, ImagePackConfig, ResourceURLs
from .utils import (
    download_file,
    extract_zip,
    extract_tar_gz,
    copy_directory,
    safe_move,
    safe_remove,
    get_gitgud_commit_hash,
)

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """版本信息记录"""

    name: str  # 资源名称
    version: str  # 版本号
    source: str = ""  # 来源（如 GitHub repo）
    filename: str = ""  # 文件名

    def __str__(self) -> str:
        if self.version and self.version != "unknown":
            return f"{self.name}: {self.version}"
        return f"{self.name}: (no version)"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "filename": self.filename,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VersionInfo":
        """从字典创建"""
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            source=data.get("source", ""),
            filename=data.get("filename", ""),
        )


def save_version_info(versions: list[VersionInfo], path: Path) -> None:
    """
    保存版本信息到 JSON 文件

    Args:
        versions: 版本信息列表
        path: 保存路径
    """
    import json

    data = [v.to_dict() for v in versions]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"版本信息已保存: {path}")


def load_version_info(path: Path) -> list[VersionInfo]:
    """
    从 JSON 文件加载版本信息

    Args:
        path: 文件路径

    Returns:
        版本信息列表
    """
    import json

    if not path.exists():
        logger.warning(f"版本信息文件不存在: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [VersionInfo.from_dict(item) for item in data]


class BeautifyHandler(ABC):
    """美化处理器基类"""

    def __init__(self, work_dir: Path, img_path: Path, urls: ResourceURLs):
        """
        初始化美化处理器

        Args:
            work_dir: 工作目录
            img_path: 目标图片目录
            urls: 资源URL配置
        """
        self.work_dir = work_dir
        self.img_path = img_path
        self.urls = urls
        self._version_info: Optional[VersionInfo] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """美化名称"""
        pass

    @property
    @abstractmethod
    def mod_code(self) -> ModCode:
        """对应的MOD代码"""
        pass

    @property
    def version_info(self) -> Optional[VersionInfo]:
        """获取版本信息"""
        return self._version_info

    @abstractmethod
    def apply(self) -> bool:
        """
        应用美化

        Returns:
            是否成功
        """
        pass

    def _get_dolp_commit_hash(self) -> Optional[str]:
        """获取 DoL+ 仓库的 commit hash"""
        return get_gitgud_commit_hash("Frostberg/degrees-of-lewdity-plus", "master")

    def download_dolp_pack(self, pack_name: str, dest_dir: Path) -> Path:
        """
        下载DoL+图片包

        Args:
            pack_name: 包名称
            dest_dir: 目标目录

        Returns:
            解压后的目录
        """
        url = self.urls.get_dolp_imagepack_url(pack_name)
        tar_path = self.work_dir / f"dolp-{pack_name}.tar.gz"
        img_dir = dest_dir / "img"

        # 检查是否已经解压过，避免重复解压
        if img_dir.exists() and (img_dir / "body").exists():
            logger.debug(f"使用缓存的 {pack_name} 图片包")
            return dest_dir

        img_dir.mkdir(parents=True, exist_ok=True)

        download_file(url, tar_path, quiet=True)

        logger.debug(f"解压 {pack_name} 图片包...")
        extract_tar_gz(tar_path, img_dir, strip_components=3)
        # safe_remove(tar_path)

        return dest_dir


class BESCHandler(BeautifyHandler):
    """BEEESSS社区精灵合集处理器"""

    @property
    def name(self) -> str:
        return "BESC"

    @property
    def mod_code(self) -> ModCode:
        return ModCode.BESC

    def apply(self) -> bool:
        logger.info(f"开始应用美化: {self.name}")

        beautify_dir = self.work_dir / "besc"
        beautify_dir.mkdir(parents=True, exist_ok=True)

        # 获取 DoL+ commit hash 作为版本
        commit_hash = self._get_dolp_commit_hash()
        if commit_hash:
            self._version_info = VersionInfo(
                name="DoL+",
                version=commit_hash,
                source="gitgud.io/Frostberg/degrees-of-lewdity-plus",
            )

        # 下载多个图片包
        packs = ["dolp", "b3s", "kaervek", "dolp_b3s"]
        for pack in packs:
            self.download_dolp_pack(pack, beautify_dir)

        # 处理大小写问题
        img_dir = beautify_dir / "img"

        # kaervek的大小写问题
        messy_curls_upper = img_dir / "hair" / "fringe" / "Messy curls"
        messy_curls_lower = img_dir / "hair" / "fringe" / "messy curls"
        if messy_curls_upper.exists():
            messy_curls_lower.mkdir(parents=True, exist_ok=True)
            for item in messy_curls_upper.iterdir():
                shutil.move(str(item), str(messy_curls_lower / item.name))
            safe_remove(messy_curls_upper)

        shoulder_upper = img_dir / "hair" / "sides" / "messy ponytail" / "Shoulder.png"
        shoulder_lower = img_dir / "hair" / "sides" / "messy ponytail" / "shoulder.png"
        safe_move(shoulder_upper, shoulder_lower)

        # 复制到目标目录
        copy_directory(img_dir, self.img_path)

        logger.info(f"完成美化: {self.name}")
        return True


class HikariHandler(BeautifyHandler):
    """Hikari特写处理器"""

    @property
    def name(self) -> str:
        return "Hikari"

    @property
    def mod_code(self) -> ModCode:
        return ModCode.SIDEVIEW_HIKARI

    def apply(self) -> bool:
        logger.info(f"开始应用美化: {self.name}")

        beautify_dir = self.work_dir / "sideview_hikari"
        beautify_dir.mkdir(parents=True, exist_ok=True)

        # 下载图片包
        packs = ["b3s_hikfem", "b3s_hikfemsubs"]
        for pack in packs:
            self.download_dolp_pack(pack, beautify_dir)

        # 处理问题文件
        img_dir = beautify_dir / "img"
        safe_remove(img_dir / "hair" / "fringe" / "Messy curls")
        safe_remove(img_dir / "clothes" / "face" / "foxmask" / "Full.png")

        # 复制到目标目录
        copy_directory(img_dir, self.img_path)

        logger.info(f"完成美化: {self.name}")
        return True


class GooseHandler(BeautifyHandler):
    """Goose特写处理器"""

    @property
    def name(self) -> str:
        return "Goose"

    @property
    def mod_code(self) -> ModCode:
        return ModCode.SIDEVIEW_GOOSE

    def apply(self) -> bool:
        logger.info(f"开始应用美化: {self.name}")

        beautify_dir = self.work_dir / "sideview_goose"
        beautify_dir.mkdir(parents=True, exist_ok=True)

        # 下载图片包
        packs = ["dolp", "goosefem", "goosefemsubs"]
        for pack in packs:
            self.download_dolp_pack(pack, beautify_dir)

        # 复制到目标目录
        img_dir = beautify_dir / "img"
        copy_directory(img_dir, self.img_path)

        logger.info(f"完成美化: {self.name}")
        return True


class UCBHandler(BeautifyHandler):
    """通用战斗美化处理器"""

    @property
    def name(self) -> str:
        return "UCB"

    @property
    def mod_code(self) -> ModCode:
        return ModCode.UCB

    def apply(self) -> bool:
        logger.info(f"开始应用美化: {self.name}")

        beautify_dir = self.work_dir / "ucb"
        beautify_dir.mkdir(parents=True, exist_ok=True)

        # 下载图片包
        self.download_dolp_pack("mysterious", beautify_dir)

        # 处理问题文件
        img_dir = beautify_dir / "img"
        safe_remove(
            img_dir / "sex" / "missionary" / "active" / "virginkiller" / "chest.png"
        )
        safe_remove(
            img_dir / "sex" / "missionary" / "active" / "virginkiller" / "waist.png"
        )

        # 复制到目标目录
        copy_directory(img_dir, self.img_path)

        logger.info(f"完成美化: {self.name}")
        return True


class AUHandler(BeautifyHandler):
    """AU特写处理器基类"""

    def __init__(
        self, work_dir: Path, img_path: Path, urls: ResourceURLs, variant: str
    ):
        """
        初始化AU处理器

        Args:
            variant: 变体类型 ("female", "male", "androgynous")
        """
        super().__init__(work_dir, img_path, urls)
        self.variant = variant

    @property
    def name(self) -> str:
        return f"AU-{self.variant[0].upper()}"

    @property
    def mod_code(self) -> ModCode:
        return {
            "female": ModCode.AU_FEMALE,
            "male": ModCode.AU_MALE,
            "androgynous": ModCode.AU_ANDROGYNOUS,
        }[self.variant]

    @property
    def asset_pattern(self) -> str:
        """获取资源文件名模式"""
        variant_map = {
            "female": "AUfemale.imgpack",
            "male": "AUmale.imgpack",
            "androgynous": "AUandrogynous.imgpack",
        }
        return variant_map[self.variant]

    def apply(self) -> bool:
        logger.info(f"开始应用美化: {self.name}")

        beautify_dir = self.work_dir / f"sideview_au_{self.variant[0]}"
        beautify_dir.mkdir(parents=True, exist_ok=True)

        # 从 GitHub Release 获取最新版本信息
        from .utils import get_github_release_asset

        asset = get_github_release_asset(
            self.urls.au_github_repo, self.asset_pattern, tag="mod"
        )

        if not asset:
            logger.error(f"无法获取 {self.name} 的下载URL")
            return False

        # 记录版本信息（无论是否使用缓存都要记录）
        self._version_info = VersionInfo(
            name=self.name,
            version=asset.version,
            source=self.urls.au_github_repo,
            filename=asset.name,
        )

        # 检查是否已经解压过，避免重复解压
        if (beautify_dir / "body").exists():
            logger.debug(f"使用缓存的 {self.name} 文件")
        else:
            # 下载并解压
            zip_path = beautify_dir / "au_imgpack.zip"
            download_file(asset.url, zip_path, quiet=True)
            logger.debug(f"解压 {self.name} 文件...")
            extract_zip(zip_path, beautify_dir)
            safe_remove(zip_path)

        # 复制到目标目录
        copy_directory(beautify_dir, self.img_path)

        logger.info(f"完成美化: {self.name}")
        return True


class SusatoHandler(BeautifyHandler):
    """Susato模型处理器"""

    @property
    def name(self) -> str:
        return "Susato"

    @property
    def mod_code(self) -> ModCode:
        return ModCode.SUSATO

    def apply(self) -> bool:
        logger.info(f"应用Susato模型 (无需额外处理)")
        # Susato只是添加后缀，不需要实际操作
        return True


class SideviewBJHandler(BeautifyHandler):
    """BJ特写处理器"""

    def __init__(
        self, work_dir: Path, img_path: Path, urls: ResourceURLs, assets_dir: Path
    ):
        super().__init__(work_dir, img_path, urls)
        self.assets_dir = assets_dir

    @property
    def name(self) -> str:
        return "Sideview-BJ"

    @property
    def mod_code(self) -> ModCode:
        return ModCode.SIDEVIEW_BJ

    def apply(self) -> bool:
        logger.info(f"开始应用美化: {self.name}")

        zip_path = self.assets_dir / "BJ_Extend.zip"
        if not zip_path.exists():
            logger.warning(f"资源文件不存在: {zip_path}")
            return False

        extract_dir = self.work_dir / "sideview_bj"
        bj_img_dir = extract_dir / "BJ_Extend" / "img"

        # 检查缓存：如果已提取过则跳过
        if bj_img_dir.exists():
            logger.debug(f"{self.name} 资源缓存命中，跳过解压")
        else:
            extract_zip(zip_path, extract_dir)

        # 复制到目标目录
        if bj_img_dir.exists():
            copy_directory(bj_img_dir, self.img_path)

        logger.info(f"完成美化: {self.name}")
        return True


class SideviewKRHandler(BeautifyHandler):
    """KR特写处理器"""

    def __init__(
        self, work_dir: Path, img_path: Path, urls: ResourceURLs, assets_dir: Path
    ):
        super().__init__(work_dir, img_path, urls)
        self.assets_dir = assets_dir

    @property
    def name(self) -> str:
        return "Sideview-KR"

    @property
    def mod_code(self) -> ModCode:
        return ModCode.SIDEVIEW_KR

    def apply(self) -> bool:
        logger.info(f"开始应用美化: {self.name}")

        zip_path = self.assets_dir / "KR_Extend.zip"
        if not zip_path.exists():
            logger.warning(f"资源文件不存在: {zip_path}")
            return False

        extract_dir = self.work_dir / "sideview_kr"
        kr_img_dir = extract_dir / "KR_Extend" / "img"

        # 检查缓存：如果已提取过则跳过
        if kr_img_dir.exists():
            logger.debug(f"{self.name} 资源缓存命中，跳过解压")
        else:
            extract_zip(zip_path, extract_dir)

        # 复制到目标目录
        if kr_img_dir.exists():
            copy_directory(kr_img_dir, self.img_path)

        logger.info(f"完成美化: {self.name}")
        return True


class BeautifyManager:
    """美化管理器"""

    def __init__(
        self,
        work_dir: Path,
        img_path: Path,
        urls: ResourceURLs,
        assets_dir: Optional[Path] = None,
    ):
        """
        初始化美化管理器

        Args:
            work_dir: 工作目录
            img_path: 目标图片目录
            urls: 资源URL配置
            assets_dir: 本地资源目录
        """
        self.work_dir = work_dir
        self.img_path = img_path
        self.urls = urls
        self.assets_dir = assets_dir or Path("assets")

        # 注册所有处理器
        self._handlers: dict[ModCode, BeautifyHandler] = {}
        self._register_handlers()

    def _register_handlers(self):
        """注册所有美化处理器"""
        self._handlers[ModCode.BESC] = BESCHandler(
            self.work_dir, self.img_path, self.urls
        )
        self._handlers[ModCode.SIDEVIEW_HIKARI] = HikariHandler(
            self.work_dir, self.img_path, self.urls
        )
        self._handlers[ModCode.SIDEVIEW_GOOSE] = GooseHandler(
            self.work_dir, self.img_path, self.urls
        )
        self._handlers[ModCode.UCB] = UCBHandler(
            self.work_dir, self.img_path, self.urls
        )
        self._handlers[ModCode.SUSATO] = SusatoHandler(
            self.work_dir, self.img_path, self.urls
        )
        self._handlers[ModCode.SIDEVIEW_BJ] = SideviewBJHandler(
            self.work_dir, self.img_path, self.urls, self.assets_dir
        )
        self._handlers[ModCode.SIDEVIEW_KR] = SideviewKRHandler(
            self.work_dir, self.img_path, self.urls, self.assets_dir
        )

        # AU变体
        self._handlers[ModCode.AU_FEMALE] = AUHandler(
            self.work_dir, self.img_path, self.urls, "female"
        )
        self._handlers[ModCode.AU_MALE] = AUHandler(
            self.work_dir, self.img_path, self.urls, "male"
        )
        self._handlers[ModCode.AU_ANDROGYNOUS] = AUHandler(
            self.work_dir, self.img_path, self.urls, "androgynous"
        )

    def apply_mods(self, mod_code: ModCode) -> tuple[list[str], list[VersionInfo]]:
        """
        应用指定的MOD

        Args:
            mod_code: MOD代码（位标志组合）

        Returns:
            (应用的MOD名称列表, 版本信息列表)
        """
        applied = []
        versions = []

        # 按照固定顺序处理MOD
        order = [
            ModCode.BESC,
            ModCode.SUSATO,
            ModCode.SIDEVIEW_BJ,
            ModCode.SIDEVIEW_KR,
            ModCode.SIDEVIEW_HIKARI,
            ModCode.SIDEVIEW_GOOSE,
            ModCode.AU_FEMALE,
            ModCode.AU_MALE,
            ModCode.AU_ANDROGYNOUS,
            ModCode.UCB,
        ]

        for code in order:
            if mod_code & code:
                handler = self._handlers.get(code)
                if handler:
                    try:
                        if handler.apply():
                            applied.append(handler.name)
                            # 收集版本信息
                            if handler.version_info:
                                versions.append(handler.version_info)
                    except Exception as e:
                        logger.error(f"应用美化失败 {handler.name}: {e}")

        # 打印版本信息摘要
        if versions:
            logger.info("=== 美化资源版本信息 ===")
            for v in versions:
                logger.info(f"  {v}")

        return applied, versions

    def get_version_summary(self) -> dict[str, str]:
        """
        获取所有已应用美化的版本摘要

        Returns:
            {美化名称: 版本号} 字典
        """
        summary = {}
        for handler in self._handlers.values():
            if handler.version_info:
                summary[handler.version_info.name] = handler.version_info.version
        return summary
