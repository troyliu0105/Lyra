"""
打包处理模块

处理ZIP和APK格式的打包。
"""

import logging
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import BuildConfig, ModCode, ResourceURLs
from .beautify import BeautifyManager, VersionInfo
from .combo import CombinationCalculator
from .utils import (
    download_file,
    extract_zip,
    create_zip,
    run_command,
    find_game_file,
    copy_directory,
    safe_remove,
)

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    """构建结果"""

    success: bool
    output_path: Optional[Path] = None
    output_name: str = ""
    error: Optional[str] = None
    applied_mods: list[str] = None
    version_info: list[VersionInfo] = None

    def __post_init__(self):
        if self.applied_mods is None:
            self.applied_mods = []
        if self.version_info is None:
            self.version_info = []


class PackageBuilder(ABC):
    """打包构建器基类"""

    def __init__(self, config: BuildConfig):
        """
        初始化构建器

        Args:
            config: 构建配置
        """
        self.config = config
        self.mod_code = ModCode(config.mod_code)

    @property
    @abstractmethod
    def pack_type(self) -> str:
        """包类型"""
        pass

    @property
    @abstractmethod
    def img_path(self) -> Path:
        """图片目录路径（相对于解压目录）"""
        pass

    def get_output_name(self, base_name: str) -> str:
        """
        生成输出文件名

        Args:
            base_name: 基础文件名

        Returns:
            完整的输出文件名
        """
        # 优先使用配置中的版本覆盖
        if self.config.dol_version and self.config.chs_version:
            dol_ver = self.config.dol_version
            chs_ver = self.config.chs_version
        else:
            # 解析版本号
            # 格式: DoL-ModLoader-X.X.X-chs-X.X.X 或类似
            match = re.search(r"DoL-ModLoader-([^-]+)-([^-]+)-([^-]+)", base_name)
            if match:
                dol_ver = match.group(2)  # 例如: v0.4.5.3
                chs_ver = match.group(3)  # 例如: alpha1.6.0
            else:
                # 尝试更简单的解析
                parts = base_name.split("-")
                dol_ver = parts[2] if len(parts) > 2 else "unknown"
                chs_ver = parts[3] if len(parts) > 3 else "unknown"

        # 构建前缀
        prefix = f"DoL-{dol_ver}-Lyra-{chs_ver}"
        if self.config.is_polyfill:
            prefix += "-polyfill"

        # 添加MOD后缀
        mod_suffix = self.mod_code.get_suffix()
        if mod_suffix:
            prefix += f"-{mod_suffix}"

        # 添加日期
        date_str = self._get_date_string()

        return f"{prefix}-{date_str}.{self.pack_type}"

    def _get_date_string(self) -> str:
        """获取日期字符串"""
        if self.config.date_param:
            if self.config.date_param.startswith("v"):
                # 从tag名提取日期
                return self.config.date_param.split("-")[-1]
            return self.config.date_param

        # 使用UTC+8时间
        tz = timezone(timedelta(hours=8))
        return datetime.now(tz).strftime("%m%d")

    def _apply_beautify(self, img_path: Path) -> tuple[list[str], list[VersionInfo]]:
        """
        应用美化MOD

        Args:
            img_path: 图片目录路径

        Returns:
            (应用的MOD名称列表, 版本信息列表)
        """
        manager = BeautifyManager(
            work_dir=self.config.temp_dir,
            img_path=img_path,
            urls=self.config.urls,
            assets_dir=Path("assets"),
        )
        return manager.apply_mods(self.mod_code)

    @abstractmethod
    def build(self, source_file: Path) -> BuildResult:
        """
        执行构建

        Args:
            source_file: 源文件路径

        Returns:
            构建结果
        """
        pass


class ZipBuilder(PackageBuilder):
    """ZIP包构建器"""

    @property
    def pack_type(self) -> str:
        return "zip"

    @property
    def img_path(self) -> Path:
        return self._work_dir / "img"

    @property
    def _work_dir(self) -> Path:
        """获取当前构建的工作目录（按pack_type和mod_code隔离）"""
        # 如果是polyfill版本，在目录中加入polyfill标记
        suffix = "-polyfill" if self.config.is_polyfill else ""
        return self.config.extract_dir / "zip" / f"{self.config.mod_code}{suffix}"

    def _get_source_file(self, source_file: Path) -> Path:
        """获取实际使用的源文件（优先使用基包）"""
        if self.config.base_zip_path and self.config.base_zip_path.exists():
            logger.info(f"使用预处理基包: {self.config.base_zip_path}")
            return self.config.base_zip_path
        return source_file

    def build(self, source_file: Path) -> BuildResult:
        """构建ZIP包"""
        actual_source = self._get_source_file(source_file)

        # 获取组合名并输出详细日志
        try:
            calculator = CombinationCalculator()
            combination_name = calculator._get_display_name(self.config.mod_code)
            logger.info(
                f"开始构建 包类型: zip, MOD代码: {self.config.mod_code}, 组合: {combination_name}"
            )
        except Exception:
            logger.info(f"开始构建 包类型: zip, MOD代码: {self.config.mod_code}")

        logger.info(f"源文件: {actual_source}")

        try:
            # 清理并创建工作目录（按mod_code隔离）
            if self._work_dir.exists():
                safe_remove(self._work_dir)
            self._work_dir.mkdir(parents=True)

            # 解压到工作目录
            extract_zip(actual_source, self._work_dir)

            # 应用美化
            applied_mods, version_info = self._apply_beautify(self.img_path)

            # 生成输出文件名
            output_name = self.get_output_name(actual_source.stem)
            output_path = self.config.output_dir / output_name

            # 创建ZIP
            create_zip(self._work_dir, output_path)

            # 清理工作目录
            safe_remove(self._work_dir)

            logger.info(f"ZIP构建完成: {output_name}")

            return BuildResult(
                success=True,
                output_path=output_path,
                output_name=output_name,
                applied_mods=applied_mods,
                version_info=version_info,
            )

        except Exception as e:
            logger.error(f"ZIP构建失败: {e}")
            # 清理工作目录
            if self._work_dir.exists():
                safe_remove(self._work_dir)
            return BuildResult(success=False, error=str(e))


class ApkBuilder(PackageBuilder):
    """APK包构建器"""

    @property
    def pack_type(self) -> str:
        return "apk"

    @property
    def img_path(self) -> Path:
        return self._work_dir / "assets" / "www" / "img"

    @property
    def _work_dir(self) -> Path:
        """获取当前构建的工作目录（按pack_type和mod_code隔离）"""
        # 如果是polyfill版本，在目录中加入polyfill标记
        suffix = "-polyfill" if self.config.is_polyfill else ""
        return self.config.extract_dir / "apk" / f"{self.config.mod_code}{suffix}"

    def _download_tools(self):
        """下载APK处理工具"""
        apktool_path = Path("apktool.jar")
        apksign_path = Path("uber-apk-signer.jar")

        if not apktool_path.exists():
            download_file(self.config.urls.apktool, apktool_path)

        if not apksign_path.exists():
            download_file(self.config.urls.apksign, apksign_path)

        return apktool_path, apksign_path

    def _decompile_apk(
        self, apk_path: Path, apktool_path: Path, dest_dir: Path
    ) -> Path:
        """反编译APK到指定目录"""
        logger.info("反编译APK...")

        if dest_dir.exists():
            safe_remove(dest_dir)

        run_command(
            ["java", "-jar", str(apktool_path), "d", str(apk_path), "-o", str(dest_dir)]
        )

        return dest_dir

    def _prepare_work_dir(self, source_file: Path, apktool_path: Path) -> Path:
        """
        准备工作目录

        根据配置决定是从已解包目录复制、解包APK，还是使用源文件
        """
        # 获取组合名
        try:
            calculator = CombinationCalculator()
            combination_name = calculator._get_display_name(self.config.mod_code)
        except Exception:
            combination_name = f"代码{self.config.mod_code}"

        # 清理并创建工作目录
        if self._work_dir.exists():
            safe_remove(self._work_dir)
        self._work_dir.mkdir(parents=True)

        # 模式1: 使用已解包的APK目录（直接复制，最快）
        if self.config.base_apk_dir and self.config.base_apk_dir.exists():
            logger.info(f"使用已解包的APK目录: {self.config.base_apk_dir}")
            copy_directory(self.config.base_apk_dir, self._work_dir)
            return self._work_dir

        # 模式2: 使用预处理的APK基包（需要解包）
        if self.config.base_apk_path and self.config.base_apk_path.exists():
            logger.info(f"使用预处理APK基包: {self.config.base_apk_path}")
            self._decompile_apk(self.config.base_apk_path, apktool_path, self._work_dir)
            return self._work_dir

        # 模式3: 独立运行模式，使用源文件（完整流程）
        logger.info(f"独立运行模式，解包源APK: {source_file}")
        self._decompile_apk(source_file, apktool_path, self._work_dir)

        # 独立运行时需要修改配置
        self._modify_manifest(self._work_dir)
        self._modify_strings(self._work_dir)

        return self._work_dir

    def _modify_manifest(self, extract_dir: Path):
        """修改AndroidManifest.xml"""
        manifest_path = extract_dir / "AndroidManifest.xml"

        if not manifest_path.exists():
            raise FileNotFoundError("AndroidManifest.xml not found")

        content = manifest_path.read_text(encoding="utf-8")

        # 修改包名
        content = content.replace('"com.vrelnir.dol"', '"com.vrelnir.dol.lyra"')
        content = content.replace('"com.vrelnir.dol_debug"', '"com.vrelnir.dol.lyra"')

        # 修改provider
        content = content.replace(
            '"com.vrelnir.dol.androidx-startup"',
            '"com.vrelnir.dol.lyra.androidx-startup"',
        )
        content = content.replace(
            '"com.vrelnir.dol_debug.androidx-startup"',
            '"com.vrelnir.dol.lyra.androidx-startup"',
        )

        manifest_path.write_text(content, encoding="utf-8")
        logger.debug("AndroidManifest.xml已修改")

    def _modify_strings(self, extract_dir: Path):
        """修改应用名称"""
        strings_path = extract_dir / "res" / "values" / "strings.xml"

        if strings_path.exists():
            content = strings_path.read_text(encoding="utf-8")
            content = content.replace("DoL", "DoL Lyra")
            content = content.replace("Degrees of Lewdity", "DoL Lyra")
            strings_path.write_text(content, encoding="utf-8")
            logger.debug("strings.xml已修改")

    def _recompile_apk(self, extract_dir: Path, apktool_path: Path) -> Path:
        """重新编译APK"""
        logger.info("重新编译APK...")

        # 使用mod_code和polyfill标记生成独立的临时文件，避免并发冲突
        suffix = "-polyfill" if self.config.is_polyfill else ""
        tmp_apk = self.config.workspace_dir / f"tmp_{self.config.mod_code}{suffix}.apk"
        run_command(
            [
                "java",
                "-jar",
                str(apktool_path),
                "b",
                str(extract_dir),
                "-o",
                str(tmp_apk),
            ]
        )

        return tmp_apk

    def _sign_apk(self, apk_path: Path, apksign_path: Path) -> Path:
        """签名APK"""
        logger.info("签名APK...")

        # 使用mod_code和polyfill标记生成独立的签名目录，避免并发冲突
        suffix = "-polyfill" if self.config.is_polyfill else ""
        signed_dir = self.config.workspace_dir / "signed" / f"{self.config.mod_code}{suffix}"
        signed_dir.mkdir(parents=True, exist_ok=True)

        run_command(
            [
                "java",
                "-jar",
                str(apksign_path),
                "-a",
                str(apk_path),
                "--ks",
                str(self.config.keystore_path),
                "--ksAlias",
                self.config.keystore_alias,
                "--ksKeyPass",
                self.config.keystore_password,
                "--ksPass",
                self.config.keystore_password,
                "-o",
                str(signed_dir),
            ]
        )

        # 查找签名后的APK
        for f in signed_dir.iterdir():
            if f.suffix == ".apk":
                return f

        raise FileNotFoundError("Signed APK not found")

    def _get_base_name(self, source_file: Path) -> str:
        """获取用于生成输出文件名的基础名"""
        # 优先使用基包名称
        if self.config.base_apk_path and self.config.base_apk_path.exists():
            return self.config.base_apk_path.stem
        if self.config.base_apk_dir and self.config.base_apk_dir.exists():
            # 从目录名推断，或使用默认名
            return self.config.base_apk_dir.name
        return source_file.stem

    def build(self, source_file: Path) -> BuildResult:
        """构建APK包"""
        # 获取组合名并输出详细日志
        try:
            calculator = CombinationCalculator()
            combination_name = calculator._get_display_name(self.config.mod_code)
            logger.info(
                f"开始构建 包类型: apk, MOD代码: {self.config.mod_code}, 组合: {combination_name}"
            )
        except Exception:
            logger.info(f"开始构建 包类型: apk, MOD代码: {self.config.mod_code}")

        try:
            # 下载工具
            apktool_path, apksign_path = self._download_tools()

            # 准备工作目录（根据配置选择模式）
            work_dir = self._prepare_work_dir(source_file, apktool_path)

            # 应用美化
            applied_mods, version_info = self._apply_beautify(self.img_path)

            # 重新编译
            tmp_apk = self._recompile_apk(work_dir, apktool_path)

            # 签名
            signed_apk = self._sign_apk(tmp_apk, apksign_path)

            # 生成输出文件名
            base_name = self._get_base_name(source_file)
            output_name = self.get_output_name(base_name)
            output_path = self.config.output_dir / output_name

            # 移动到输出目录
            shutil.move(str(signed_apk), str(output_path))

            # 清理临时文件（使用mod_code和polyfill特定的路径）
            suffix = "-polyfill" if self.config.is_polyfill else ""
            safe_remove(tmp_apk)
            safe_remove(
                self.config.workspace_dir / "signed" / f"{self.config.mod_code}{suffix}"
            )
            safe_remove(self._work_dir)

            logger.info(f"APK构建完成: {output_name}")

            return BuildResult(
                success=True,
                output_path=output_path,
                output_name=output_name,
                applied_mods=applied_mods,
                version_info=version_info,
            )

        except Exception as e:
            logger.error(f"APK构建失败: {e}")
            # 清理工作目录
            if self._work_dir.exists():
                safe_remove(self._work_dir)
            return BuildResult(success=False, error=str(e))


def create_builder(config: BuildConfig) -> PackageBuilder:
    """
    创建打包构建器

    Args:
        config: 构建配置

    Returns:
        对应类型的构建器
    """
    builders = {
        "zip": ZipBuilder,
        "apk": ApkBuilder,
    }

    builder_class = builders.get(config.pack_type.lower())
    if not builder_class:
        raise ValueError(f"不支持的包类型: {config.pack_type}")

    return builder_class(config)
