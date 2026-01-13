"""
DoL-Lyra 整合包构建工具

一个用于构建 Degrees of Lewdity 汉化整合包的自动化工具。
支持多种MOD组合、ZIP和APK打包格式。
配置驱动，支持从 TOML 文件加载配置。
"""

__version__ = "1.0.0"
__author__ = "DoL-Lyra"

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

from .combo import (
    CombinationCalculator,
    ModCombination,
    get_default_combinations,
    get_default_build_codes,
)

from .gen_page import (
    DownloadPageConfig,
    DownloadPageGenerator,
    generate_download_page,
)

__all__ = [
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
