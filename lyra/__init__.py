"""
DoL-Lyra 构建系统

一个用于构建 Degrees of Lewdity 汉化整合包的自动化工具。
支持多种MOD组合、ZIP和APK打包格式。
配置驱动，完全由 CI 控制流程。

主要模块：
- paths: 路径管理
- version: 版本信息管理
- downloader: 资源下载
- warmup: 资源预热
- prepare: 游戏预处理
- build: 构建器
- parallel: 并行构建
- combo: 组合计算
- gen_page: 页面生成
"""

__version__ = "2.0.0"
__author__ = "DoL-Lyra"

# 路径管理
from .paths import BuildPaths

# 版本信息
from .version import (
    LyraVersion,
    VersionInfo,
    VersionRegistry,
)

# 配置加载
from .config_loader import (
    ConfigLoader,
    Feature,
    CombinationsConfig,
    BuildConfiguration,
    get_config_loader,
    load_features,
    load_combinations_config,
    load_build_config,
)

# 组合计算
from .combo import (
    CombinationCalculator,
    ModCombination,
    get_default_combinations,
    get_default_build_codes,
)

# 页面生成
from .gen_page import (
    DownloadPageConfig,
    DownloadPageGenerator,
    generate_download_page,
)

__all__ = [
    # Paths
    "BuildPaths",
    # Version
    "LyraVersion",
    "VersionInfo",
    "VersionRegistry",
    # Config Loader
    "ConfigLoader",
    "Feature",
    "CombinationsConfig",
    "BuildConfiguration",
    "get_config_loader",
    "load_features",
    "load_combinations_config",
    "load_build_config",
    # Combinations
    "CombinationCalculator",
    "ModCombination",
    "get_default_combinations",
    "get_default_build_codes",
    # Download Page
    "DownloadPageConfig",
    "DownloadPageGenerator",
    "generate_download_page",
]
