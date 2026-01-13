"""
配置管理模块

集中管理所有可配置的选项，包括MOD代码定义、资源URL等。
支持从 TOML 配置文件加载配置。
"""

from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import Optional


from .config_loader import (
    load_build_config,
    BuildConfiguration,
)


class ModCode(IntFlag):
    """MOD代码位标志定义"""
    BESC = 1        # BEEESSS社区精灵合集
    CHEAT = 2       # 作弊功能
    CSD = 4         # CSD
    SIDEVIEW_BJ = 8       # BJ特写
    SIDEVIEW_KR = 16      # KR特写
    SIDEVIEW_HIKARI = 32  # Hikari特写
    WAX = 64              # WAX美化
    SUSATO = 128          # Susato模型
    UCB = 256             # 通用战斗美化
    SIDEVIEW_GOOSE = 512  # Goose特写
    AU_FEMALE = 1024      # AU女性
    AU_MALE = 2048        # AU男性
    AU_ANDROGYNOUS = 4096 # AU双性

    @classmethod
    def from_string(cls, code_str: str) -> tuple['ModCode', bool]:
        """
        从字符串解析MOD代码
        
        Args:
            code_str: MOD代码字符串，可以是数字或 "polyfill-数字" 格式
            
        Returns:
            (ModCode, is_polyfill) 元组
        """
        is_polyfill = False
        if code_str.startswith("polyfill-"):
            is_polyfill = True
            code_str = code_str.split("-")[1]
        
        return cls(int(code_str)), is_polyfill

    def get_suffix(self) -> str:
        """获取基于MOD代码的文件名后缀"""
        suffix_parts = []
        
        if self & ModCode.BESC:
            suffix_parts.append("besc")
        if self & ModCode.SUSATO:
            suffix_parts.append("susato")
        if self & ModCode.SIDEVIEW_BJ:
            suffix_parts.append("sideviewbj")
        if self & ModCode.SIDEVIEW_KR:
            suffix_parts.append("sideviewkr")
        if self & ModCode.SIDEVIEW_HIKARI:
            suffix_parts.append("hikari")
        if self & ModCode.SIDEVIEW_GOOSE:
            suffix_parts.append("goose")
        if self & ModCode.AU_FEMALE:
            suffix_parts.append("au-f")
        if self & ModCode.AU_MALE:
            suffix_parts.append("au-m")
        if self & ModCode.AU_ANDROGYNOUS:
            suffix_parts.append("au-a")
        if self & ModCode.UCB:
            suffix_parts.append("ucb")
        
        return "-".join(suffix_parts) if suffix_parts else ""


@dataclass
class ResourceURLs:
    """资源下载URL配置（从TOML配置文件加载）"""
    # 工具
    apktool: str
    apksign: str
    
    # DoL+ 资源基础URL
    dolp_base: str
    
    # AU特写资源
    au_female: str
    au_male: str
    au_androgynous: str
    
    def get_dolp_imagepack_url(self, pack_name: str) -> str:
        """获取DoL+图片包的完整URL"""
        return f"{self.dolp_base}/{pack_name}"
    
    @classmethod
    def from_config(cls) -> 'ResourceURLs':
        """从配置文件加载"""
        config = load_build_config()
        
        return cls(
            apktool=config.apktool_url,
            apksign=config.uber_apk_signer_url,
            dolp_base=config.dolp_base_url,
            au_female=config.au_f_url,
            au_male=config.au_m_url,
            au_androgynous=config.au_a_url,
        )


def _get_default_resource_urls() -> ResourceURLs:
    """获取默认资源URL（从配置文件加载）"""
    return ResourceURLs.from_config()


def _get_default_workspace_dir() -> Path:
    """获取默认工作目录（从配置文件加载）"""
    from .config_loader import load_build_config
    config = load_build_config()
    return Path(config.workspace_dir)


def _get_default_output_dir() -> Path:
    """获取默认输出目录（从配置文件加载）"""
    from .config_loader import load_build_config
    config = load_build_config()
    return Path(config.output_dir)


def _get_default_extract_dir() -> Path:
    """获取默认解压目录（从配置文件加载）"""
    from .config_loader import load_build_config
    config = load_build_config()
    workspace = Path(config.workspace_dir)
    return workspace / config.extract_dir


def _get_default_temp_dir() -> Path:
    """获取默认临时目录（从配置文件加载）"""
    from .config_loader import load_build_config
    config = load_build_config()
    workspace = Path(config.workspace_dir)
    return workspace / config.temp_dir


@dataclass
class BuildConfig:
    """构建配置"""
    # 目录配置
    workspace_dir: Path = field(default_factory=_get_default_workspace_dir)
    extract_dir: Path = field(default_factory=_get_default_extract_dir)
    output_dir: Path = field(default_factory=_get_default_output_dir)
    temp_dir: Path = field(default_factory=_get_default_temp_dir)
    
    # 构建参数
    pack_type: str = "zip"  # zip 或 apk
    mod_code: int = 0
    date_param: Optional[str] = None
    is_polyfill: bool = False
    
    # 基包路径（可选，用于CI预处理模式）
    base_zip_path: Optional[Path] = None      # 预处理的zip基包路径
    base_apk_path: Optional[Path] = None      # 预处理的apk基包路径（需要解包）
    base_apk_dir: Optional[Path] = None       # 已解包的apk目录（不需要解包，直接复制）
    
    # 版本覆盖（可选，用于CI模式指定固定版本）
    dol_version: Optional[str] = None         # DoL版本（如 0.5.7.9）
    chs_version: Optional[str] = None         # 汉化版本（如 5.0.2a）
    
    # APK签名配置
    keystore_path: Path = field(default_factory=lambda: Path("dol.jks"))
    keystore_alias: str = "dol"
    keystore_password: str = "dolchs"
    
    # 资源URL（从配置文件加载）
    urls: ResourceURLs = field(default_factory=_get_default_resource_urls)
    
    def __post_init__(self):
        """确保目录存在"""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.extract_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class ImagePackConfig:
    """图片包配置"""
    name: str
    urls: list[str]
    case_fixes: dict[str, str] = field(default_factory=dict)  # 源路径 -> 目标路径
    files_to_remove: list[str] = field(default_factory=list)
    
    @classmethod
    def get_all_packs(cls, config: Optional[BuildConfiguration] = None) -> dict[str, 'ImagePackConfig']:
        """
        获取所有预定义的图片包配置
        
        优先从配置文件加载，如果配置文件中没有则使用默认值。
        """
        if config is None:
            try:
                config = load_build_config()
            except Exception:
                config = None
        
        # 如果配置中有 imagepacks，使用配置中的
        if config and config.imagepacks:
            result = {}
            for name, pack in config.imagepacks.items():
                result[name] = cls(
                    name=pack.name,
                    urls=pack.urls,
                    case_fixes=pack.case_fixes,
                    files_to_remove=pack.files_to_remove,
                )
            return result
        
        # 否则使用默认值
        base_url = "https://gitgud.io/Frostberg/degrees-of-lewdity-plus/-/archive/master/degrees-of-lewdity-plus-master.tar.gz?path=imagepacks"
        
        return {
            'besc': cls(
                name='besc',
                urls=[
                    f"{base_url}/dolp",
                    f"{base_url}/b3s",
                    f"{base_url}/kaervek",
                    f"{base_url}/dolp_b3s",
                ],
                case_fixes={
                    "img/hair/fringe/Messy curls": "img/hair/fringe/messy curls",
                    "img/hair/sides/messy ponytail/Shoulder.png": "img/hair/sides/messy ponytail/shoulder.png",
                },
            ),
            'hikari': cls(
                name='hikari',
                urls=[
                    f"{base_url}/b3s_hikfem",
                    f"{base_url}/b3s_hikfemsubs",
                ],
                files_to_remove=[
                    "img/hair/fringe/Messy curls",
                    "img/clothes/face/foxmask/Full.png",
                ],
            ),
            'goose': cls(
                name='goose',
                urls=[
                    f"{base_url}/dolp",
                    f"{base_url}/goosefem",
                    f"{base_url}/goosefemsubs",
                ],
            ),
            'ucb': cls(
                name='ucb',
                urls=[
                    f"{base_url}/mysterious",
                ],
                files_to_remove=[
                    "img/sex/missionary/active/virginkiller/chest.png",
                    "img/sex/missionary/active/virginkiller/waist.png",
                ],
            ),
        }


def get_build_matrix() -> list[str]:
    """
    获取构建矩阵（用于GitHub Actions）
    
    动态计算有效的MOD组合代码列表。
    """
    from .combo import get_default_build_codes
    return get_default_build_codes()
