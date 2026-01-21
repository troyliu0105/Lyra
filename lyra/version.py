"""
版本信息管理模块

统一管理构建过程中的版本信息记录。
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LyraVersion:
    """
    Lyra版本信息

    从tag字符串解析，格式: v{dol_ver}-{chs_ver}-{date}
    例如: v0.5.7.9-5.0.2a-0112
    """

    dol_ver: str  # DoL版本号，如 0.5.7.9
    chs_ver: str  # 汉化版本号，如 5.0.2a
    date: str  # 日期，如 0112

    @classmethod
    def from_tag(cls, tag: str) -> "LyraVersion":
        """
        从tag字符串解析版本信息

        Args:
            tag: 版本tag，格式如 v0.5.7.9-5.0.2a-0112

        Returns:
            LyraVersion实例

        Raises:
            ValueError: 如果tag格式不正确
        """
        ver_str = tag[1:] if tag.startswith("v") else tag
        parts = ver_str.split("-")
        if len(parts) >= 3:
            return cls(dol_ver=parts[0], chs_ver=parts[1], date=parts[2])
        else:
            raise ValueError(f"无法从版本字符串中提取版本信息: {tag}")

    @property
    def tag(self) -> str:
        """返回完整的tag字符串"""
        return f"v{self.dol_ver}-{self.chs_ver}-{self.date}"

    def __str__(self) -> str:
        return self.tag


@dataclass
class VersionInfo:
    """
    资源版本信息记录

    用于记录各种资源（汉化仓库、美化包等）的版本信息。
    """

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


@dataclass
class VersionRegistry:
    """
    版本信息注册表

    用于收集和管理构建过程中的所有版本信息。
    """

    versions: list[VersionInfo] = field(default_factory=list)

    def add(self, info: VersionInfo):
        """添加版本信息"""
        # 避免重复添加
        for v in self.versions:
            if v.name == info.name:
                # 更新已存在的版本信息
                v.version = info.version
                v.source = info.source
                v.filename = info.filename
                return
        self.versions.append(info)

    def extend(self, infos: list[VersionInfo]):
        """批量添加版本信息"""
        for info in infos:
            self.add(info)

    def save(self, path: Path):
        """
        保存版本信息到JSON文件

        Args:
            path: 保存路径
        """
        data = [v.to_dict() for v in self.versions]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"版本信息已保存: {path}")

    @classmethod
    def load(cls, path: Path) -> "VersionRegistry":
        """
        从JSON文件加载版本信息

        Args:
            path: 文件路径

        Returns:
            VersionRegistry实例
        """
        if not path.exists():
            logger.warning(f"版本信息文件不存在: {path}")
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        versions = [VersionInfo.from_dict(item) for item in data]
        return cls(versions=versions)

    def print_summary(self):
        """打印版本信息摘要"""
        if not self.versions:
            return
        logger.info("=== 版本信息汇总 ===")
        for v in self.versions:
            logger.info(f"  {v}")

    def __len__(self) -> int:
        return len(self.versions)

    def __iter__(self):
        return iter(self.versions)
