# DoL-Lyra 构建系统文档

## 目录

- [简介](#简介)
- [快速开始](#快速开始)
- [功能特性](#功能特性)
- [环境准备](#环境准备)
- [构建命令](#构建命令)
  - [build.py - 独立构建工具](#buildpy---独立构建工具)
  - [ci.py - CI/CD 辅助脚本](#cipy---cicd-辅助脚本)
- [MOD 代码说明](#mod-代码说明)
- [配置文件](#配置文件)
- [并行构建](#并行构建)
- [高级用法](#高级用法)
- [故障排查](#故障排查)
- [开发指南](#开发指南)

---

## 简介

DoL-Lyra 构建系统是一个自动化工具，用于生成 Degrees of Lewdity 游戏的各种 MOD 组合包。支持：

- **多种 MOD 组合**：13+ 种不同的 MOD 可自由组合
- **双平台支持**：ZIP（PC/Web）和 APK（Android）
- **批量构建**：一键生成所有组合
- **并行构建**：多核 CPU 加速构建
- **版本管理**：支持版本号和日期标记
- **CI/CD 集成**：GitHub Actions 自动化发布

### 架构概览

```
lyra/
├── builder.py         # 核心构建逻辑（ZipBuilder, ApkBuilder）
├── beautify.py        # 美化资源管理（各种 Handler）
├── combinations.py    # MOD 组合计算
├── config.py          # 配置数据结构
├── config_loader.py   # 配置文件加载
├── download_page.py   # 下载页面生成
└── utils.py           # 工具函数

scripts/
└── ci.py             # GitHub Actions 辅助脚本

config/
├── build.toml        # 构建配置（URL、路径、APK 替换规则）
├── features.toml     # MOD 功能定义
└── combinations.toml # MOD 组合规则

build.py              # 命令行入口
```

---

## 快速开始

### 最简单的用法

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备游戏文件
# 将 DoL-xxx.zip 和 DoL-xxx.apk 放在项目根目录

# 3. 构建单个包
python build.py zip 3           # BESC+作弊 ZIP包
python build.py apk 514         # BESC+作弊+Hikari APK包

# 4. 查看输出
ls output/
```

### CI/CD 工作流

```bash
# 1. 准备基包（只需执行一次）
python scripts/ci.py prepare-package

# 2. 批量构建所有组合
python scripts/ci.py build-all-parallel --tag v0.5.7.9-5.0.2a-0113 --jobs 8

# 3. 生成下载页面
python scripts/ci.py generate-page --version v0.5.7.9-5.0.2a-0113 -o index.md
```

---

## 功能特性

### 1. 灵活的 MOD 组合

通过位运算实现的 MOD 代码系统：

- 每个 MOD 占用一个二进制位（1, 2, 4, 8, 16...）
- 组合 MOD 只需相加（BESC=1 + 作弊=2 = 3）
- 支持 13 个 MOD，超过 8000 种理论组合
- 配置驱动：通过 `combinations.toml` 定义有效组合

### 2. 双构建器架构

**ZipBuilder**：Web/PC 平台

- 解压 → 美化 → 压缩
- 支持基包复用（`--base-zip`）
- 快速构建（无需 Java）

**ApkBuilder**：Android 平台

- 反编译 → 美化 → 重编译 → 签名
- 支持三种模式：
  - 独立模式：完整流程
  - 基包模式：从预处理 APK 构建（`--base-apk`）
  - 目录模式：从已解包目录构建（`--base-apk-dir`，最快）

### 3. 智能缓存系统

**资源下载缓存**：

- 检查文件是否存在，避免重复下载
- DOLP 图包缓存：检查 `img/body/` 目录
- AU 变体缓存：检查 `body/` 目录
- Sideview 缓存：检查特定 `img/` 目录

**并发安全**：

- 幂等操作：重复执行结果相同
- 覆盖安全：多进程同时下载，先完成者胜出

### 4. 并行构建引擎

**性能优化**：

- 使用 `ProcessPoolExecutor` 多进程并行
- 工作目录完全隔离（`extract/{pack_type}/{mod_code}/`）
- 临时文件独立命名（`tmp_{mod_code}.apk`）
- 预期 2-6 倍加速（取决于 CPU 核心数）

**并发安全保障**：

- 二级目录隔离：pack_type + mod_code
- 独立临时文件：每个任务独立命名
- 进程级异常处理：单个失败不影响其他任务

---

## 环境准备

### 系统要求

- **操作系统**：Linux / macOS / Windows (WSL)
- **Python**：3.8+
- **Java**：17+（APK 构建需要）

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/DoL-Lyra/Lyra.git
cd Lyra

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 验证 Java 环境（APK 构建需要）
java -version
# 应显示 Java 17 或更高版本

# 4. 准备游戏文件
# 下载最新的 DoL 游戏包：
# - DoL-xxx.zip（正常版）
# - DoL-xxx-polyfill.zip（polyfill 版，可选）
# - DoL-xxx.apk（Android 版，可选）
# 放在项目根目录

# 5. 测试构建
python build.py zip 3 -v
```

---

## 构建命令

### build.py - 独立构建工具

**用途**：单次构建或手动构建

#### 基本语法

```bash
python build.py <pack_type> <mod_code> [date] [options]
```

#### 参数说明

| 参数 | 必需 | 说明 | 示例 |
|------|------|------|------|
| `pack_type` | 是 | 包类型：`zip` 或 `apk` | `zip` |
| `mod_code` | 是 | MOD 代码或 `all` | `3`, `514`, `all` |
| `date` | 否 | 日期标记（MMDD）| `0113` |
| `-v, --verbose` | 否 | 详细日志 | |
| `-o, --output` | 否 | 输出目录 | `-o output/` |
| `--base-zip` | 否 | ZIP 基包路径 | `--base-zip base.zip` |
| `--base-apk` | 否 | APK 基包路径 | `--base-apk base.apk` |
| `--base-apk-dir` | 否 | 已解包 APK 目录 | `--base-apk-dir apk/` |
| `--dol-version` | 否 | DoL 版本号 | `--dol-version 0.5.7.9` |
| `--chs-version` | 否 | 汉化版本号 | `--chs-version 5.0.2a` |
| `--list-combinations` | 否 | 列出所有组合 | |
| `--generate-page` | 否 | 生成下载页面 | `--generate-page v1.0.0` |

#### 使用示例

```bash
# 构建单个 ZIP 包
python build.py zip 3

# 构建 APK，指定日期
python build.py apk 514 0113

# 构建 polyfill 版本
python build.py zip polyfill-3

# 使用基包加速（ZIP）
python build.py zip 3 --base-zip workspace/base/base.zip

# 使用已解包目录加速（APK，最快）
python build.py apk 514 --base-apk-dir workspace/prepare_package/apk

# 指定版本号
python build.py zip 3 --dol-version 0.5.7.9 --chs-version 5.0.2a

# 批量构建所有组合
python build.py zip all

# 列出所有可用组合
python build.py --list-combinations

# 生成下载页面
python build.py --generate-page v0.5.7.9-5.0.2a-0113 -o download.md

# 详细日志模式
python build.py zip 3 -v
```

---

### ci.py - CI/CD 辅助脚本

**用途**：GitHub Actions 工作流和批量构建

#### 可用命令

```bash
python scripts/ci.py <command> [options]
```

| 命令 | 说明 |
|------|------|
| `prepare-package` | 准备基包（解包、修改、重打包）|
| `build` | 构建单个包 |
| `build-all` | 顺序批量构建所有组合 |
| `build-all-parallel` | **并行**批量构建所有组合 |
| `generate-matrix` | 生成构建矩阵（GitHub Actions）|
| `generate-page` | 生成下载页面 |
| `list-combinations` | 列出所有组合 |
| `check-update` | 检查是否需要更新 |

#### 1. prepare-package - 准备基包

**用途**：一次性准备，后续快速复用

```bash
python scripts/ci.py prepare-package [options]
```

**功能**：

- 解压 ZIP 和 APK
- 应用 APK 修改（包名、版本号等）
- 生成基包：`base.zip`, `base.apk`, `base-polyfill.zip`, `base-polyfill.apk`
- 保留已解包目录：`apk/`, `apk-polyfill/`

**输出结构**：

```
workspace/
├── base/
│   ├── base.zip              # ZIP 基包
│   ├── base-polyfill.zip     # polyfill ZIP 基包
│   ├── base.apk              # APK 基包（已修改）
│   ├── base-polyfill.apk     # polyfill APK 基包
│   └── names.json            # 基包名称映射
└── prepare_package/
    ├── apk/                  # 已解包的正常版 APK
    └── apk-polyfill/         # 已解包的 polyfill APK
```

**参数**：

```bash
--workspace DIR   # 工作目录（默认当前目录）
-v, --verbose     # 详细日志
```

**示例**：

```bash
# 准备基包
python scripts/ci.py prepare-package -v

# 指定工作目录
python scripts/ci.py prepare-package --workspace /path/to/workspace
```

#### 2. build-all - 顺序批量构建

**用途**：顺序构建所有组合（适合调试）

```bash
python scripts/ci.py build-all [pack_type] [date] [options]
```

**参数**：

```bash
pack_type         # 可选：zip 或 apk（不指定则两种都构建）
date             # 可选：日期（MMDD）
--tag TAG        # Tag 格式：v0.5.7.9-5.0.2a-0113
--workspace DIR  # 工作目录
-v, --verbose    # 详细日志
```

**示例**：

```bash
# 构建所有 ZIP 和 APK
python scripts/ci.py build-all --tag v0.5.7.9-5.0.2a-0113

# 仅构建 ZIP
python scripts/ci.py build-all zip --tag v0.5.7.9-5.0.2a-0113

# 指定日期
python scripts/ci.py build-all 0113 -v
```

#### 3. build-all-parallel - 并行批量构建 ⚡

**用途**：多核并行构建，速度提升 2-6 倍

```bash
python scripts/ci.py build-all-parallel [pack_type] [date] [options]
```

**参数**：

```bash
pack_type         # 可选：zip 或 apk
date             # 可选：日期（MMDD）
--tag TAG        # Tag 格式：v0.5.7.9-5.0.2a-0113
--jobs N, -j N   # 并发进程数（默认：min(cpu_count, 4)）
--workspace DIR  # 工作目录
-v, --verbose    # 详细日志
```

**示例**：

```bash
# 使用 8 个进程并行构建
python scripts/ci.py build-all-parallel --tag v0.5.7.9-5.0.2a-0113 --jobs 8

# 仅构建 APK，4 个进程
python scripts/ci.py build-all-parallel apk --jobs 4

# 自动选择并发数
python scripts/ci.py build-all-parallel --tag v0.5.7.9-5.0.2a-0113
```

**性能对比**：

| 构建方式 | 耗时（52 个任务） | 并发数 | 加速比 |
|---------|-----------------|--------|--------|
| build-all | ~120 分钟 | 1 | 1x |
| build-all-parallel -j 2 | ~70 分钟 | 2 | 1.7x |
| build-all-parallel -j 4 | ~40 分钟 | 4 | 3x |
| build-all-parallel -j 8 | ~35 分钟 | 8 | 3.4x |

#### 4. generate-page - 生成下载页面

```bash
python scripts/ci.py generate-page --version VERSION [options]
```

**参数**：

```bash
--version VER     # 版本号（必需）
--output FILE     # 输出文件（可选，默认打印到标准输出）
--github-owner    # GitHub 用户名（默认：sakarie9）
--github-repo     # GitHub 仓库名（默认：DoL-Lyra）
-v, --verbose     # 详细日志
```

**示例**：

```bash
# 生成下载页面到文件
python scripts/ci.py generate-page \
  --version v0.5.7.9-5.0.2a-0113 \
  --output download.md

# 打印到标准输出
python scripts/ci.py generate-page --version v0.5.7.9-5.0.2a-0113
```

#### 5. 其他命令

```bash
# 列出所有组合
python scripts/ci.py list-combinations

# 生成构建矩阵（GitHub Actions）
python scripts/ci.py generate-matrix

# 检查是否需要更新
python scripts/ci.py check-update
```

---

## MOD 代码说明

### 代码表

| MOD 名称 | 代码 | 说明 |
|---------|------|------|
| BESC | 1 | BEEESSS 社区精灵合集 |
| 作弊 | 2 | 作弊功能模块 |
| CSD | 4 | CSD 功能 |
| Sideview-BJ | 8 | BJ 特写 |
| Sideview-KR | 16 | KR 特写 |
| Sideview-Hikari | 32 | Hikari 特写 |
| WAX | 64 | WAX 美化 |
| Susato | 128 | Susato 模型 |
| UCB | 256 | 通用战斗美化 |
| Sideview-Goose | 512 | Goose 特写 |
| AU-Female | 1024 | AU 女性变体 |
| AU-Male | 2048 | AU 男性变体 |
| AU-Androgynous | 4096 | AU 双性变体 |

### 代码计算

MOD 代码通过**位运算**计算：

```python
# 示例 1：BESC + 作弊
code = 1 + 2 = 3

# 示例 2：BESC + 作弊 + Hikari
code = 1 + 2 + 32 = 35

# 示例 3：BESC + 作弊 + Hikari + UCB
code = 1 + 2 + 32 + 256 = 291

# 示例 4：完整配置
code = 1 + 2 + 4 + 8 + 16 + 32 + 64 + 128 + 256 + 512 + 1024 = 2047
```

### 常用组合

| 代码 | 组合名称 | 说明 |
|------|---------|------|
| 3 | BESC+作弊 | 基础组合 |
| 7 | BESC+作弊+CSD | 添加 CSD |
| 35 | BESC+作弊+Hikari | 添加 Hikari 特写 |
| 259 | BESC+作弊+UCB | 添加战斗美化 |
| 514 | 作弊+Hikari+UCB | 无 BESC 的组合 |
| 1026 | 作弊+Hikari+AU女性 | AU 女性变体 |
| 2050 | 作弊+Hikari+AU男性 | AU 男性变体 |
| 4098 | 作弊+Hikari+AU双性 | AU 双性变体 |

### Polyfill 版本

在 MOD 代码前添加 `polyfill-` 前缀：

```bash
# 正常版
python build.py zip 3

# Polyfill 版
python build.py zip polyfill-3
```

---

## 配置文件

### config/build.toml

**用途**：构建过程配置

```toml
[urls]
# 工具下载地址
apktool = "https://github.com/.../apktool_2.12.0.jar"
uber_apk_signer = "https://github.com/.../uber-apk-signer-1.3.0.jar"

# 资源包地址
dolp_base = "https://gitgud.io/.../degrees-of-lewdity-plus-master.tar.gz"
au_f = "https://github.com/.../AUfemale.imgpack.zip"
au_m = "https://github.com/.../AUmale.imgpack.zip"
au_a = "https://github.com/.../AUandrogynous.imgpack.zip"

[paths]
android_save_patch = "patches/0001-dol-android-save-to-file.patch"
workspace = "workspace"
output = "output"

[github]
owner = "sakarie9"
repo = "DoL-Lyra"

# APK 包名替换规则
[[apk.replacements]]
file = "AndroidManifest.xml"
pattern = '"com.vrelnir.dol"'
replacement = '"com.vrelnir.dol.lyra"'
```

### config/features.toml

**用途**：MOD 功能定义

```toml
[[feature]]
name = "BESC"
code = 1
display_name = "BESC"
description = "BEEESSS社区精灵合集"

[[feature]]
name = "作弊"
code = 2
display_name = "作弊"
description = "作弊功能"
```

### config/combinations.toml

**用途**：定义有效的 MOD 组合和互斥规则

```toml
[rules]
# 推荐组合（优先显示）
recommended = [3, 35, 259, 514, 1026, 2050, 4098]

# 必须包含的 MOD（通常是作弊）
must_include = [2]

# 互斥组（不能同时启用）
[[rules.exclusive_groups]]
mods = [1024, 2048, 4096]  # AU 三个变体互斥
reason = "AU变体互斥"
```

---

## 并行构建

### 原理

使用 Python `ProcessPoolExecutor` 实现多进程并行：

- 每个 MOD 代码独立进程
- 完全隔离的工作目录
- 异步结果收集

### 并发安全设计

#### 1. 工作目录隔离

```
workspace/
├── extract/
│   ├── zip/              # ZIP 构建专用
│   │   ├── 3/
│   │   ├── 514/
│   │   └── 4098/
│   └── apk/              # APK 构建专用
│       ├── 3/
│       ├── 514/
│       └── 4098/
```

#### 2. 临时文件命名

- APK 临时文件：`workspace/tmp_{mod_code}.apk`
- 签名输出目录：`workspace/signed/{mod_code}/`

#### 3. 资源缓存

- 下载前检查文件存在
- 解压前检查目录存在
- 幂等操作：重复执行安全

### 性能优化建议

| 场景 | 推荐并发数 | 说明 |
|------|-----------|------|
| 开发环境（16GB 内存）| `-j 8` | CPU 核心数 |
| CI 环境（8GB 内存）| `-j 4` | 避免 OOM |
| 低配环境（4GB 内存）| `-j 2` | 保守配置 |
| 高性能服务器 | `-j 16` | CPU 核心数 × 1.5 |

### 并发问题排查

**问题 1：内存不足（OOM）**

```bash
# 解决：减少并发数
python scripts/ci.py build-all-parallel --jobs 2
```

**问题 2：磁盘 I/O 瓶颈**

```bash
# 解决：使用 SSD，或减少并发数
python scripts/ci.py build-all-parallel --jobs 4
```

**问题 3：部分任务失败**

```bash
# 查看详细日志
python scripts/ci.py build-all-parallel -v

# 单独重试失败的任务
python build.py apk 4098 -v
```

---

## 高级用法

### 1. 自定义 MOD 组合

编辑 `config/combinations.toml`：

```toml
# 添加新的推荐组合
[rules]
recommended = [3, 35, 259, 514, 1026, 2050, 4098, 1027]  # 添加 1027

# 添加互斥规则
[[rules.exclusive_groups]]
mods = [8, 16]  # BJ 和 KR 互斥
reason = "Sideview 互斥"
```

### 2. 自定义资源 URL

编辑 `config/build.toml`：

```toml
[urls]
# 使用自己的镜像
dolp_base = "https://your-mirror.com/dolp.tar.gz"
au_f = "https://your-cdn.com/AUfemale.zip"
```

### 3. 修改 APK 包名

编辑 `config/build.toml`：

```toml
[[apk.replacements]]
file = "AndroidManifest.xml"
pattern = '"com.vrelnir.dol"'
replacement = '"com.yourname.dol"'  # 自定义包名
```

### 4. 添加新的美化 MOD

1. 在 `config/features.toml` 添加定义：

```toml
[[feature]]
name = "NewMod"
code = 8192  # 下一个 2 的幂
display_name = "新 MOD"
description = "新 MOD 说明"
```

1. 在 `lyra/beautify.py` 添加 Handler：

```python
class NewModHandler(BeautifyHandler):
    @property
    def name(self) -> str:
        return "NewMod"
    
    @property
    def mod_code(self) -> ModCode:
        return ModCode.NEW_MOD
    
    def apply(self) -> bool:
        # 实现美化逻辑
        pass
```

1. 在 `lyra/config.py` 添加枚举：

```python
class ModCode(IntEnum):
    # ... existing codes ...
    NEW_MOD = 8192
```

---

## 故障排查

### 常见问题

#### 1. Java 相关错误

**症状**：`java: command not found` 或 APK 构建失败

**解决**：

```bash
# 安装 Java 17+
# Ubuntu/Debian
sudo apt install openjdk-17-jdk

# macOS
brew install openjdk@17

# 验证
java -version
```

#### 2. 内存不足

**症状**：进程被杀死，`Killed` 或 `OOM`

**解决**：

```bash
# 减少并发数
python scripts/ci.py build-all-parallel --jobs 2

# 或使用顺序构建
python scripts/ci.py build-all
```

#### 3. APK 签名失败

**症状**：`uber-apk-signer.jar returned non-zero exit status`

**原因**：已在并行构建中修复（使用独立目录）

**验证**：

```bash
# 检查是否使用最新代码
grep "signed_{mod_code}" lyra/builder.py

# 应该看到：signed_dir = Path("signed") / str(self.config.mod_code)
```

#### 4. 资源下载失败

**症状**：`Failed to download` 或超时

**解决**：

```bash
# 方法 1：重试
python build.py zip 3

# 方法 2：使用代理
export HTTP_PROXY=http://proxy:port
python build.py zip 3

# 方法 3：手动下载后放到正确位置
# 查看日志获取 URL 和目标路径
```

#### 5. 文件不存在

**症状**：`FileNotFoundError: DoL-xxx.zip`

**解决**：

```bash
# 确保游戏文件在项目根目录
ls -la DoL*.zip DoL*.apk

# 或使用基包模式
python scripts/ci.py prepare-package
python build.py zip 3 --base-zip workspace/base/base.zip
```

### 调试技巧

```bash
# 1. 使用详细日志
python build.py zip 3 -v

# 2. 查看临时文件
ls -la workspace/extract/zip/3/
ls -la workspace/signed/3/
ls -la workspace/tmp_3.apk

# 3. 单独测试组件
python -c "from lyra.combinations import CombinationCalculator; print(CombinationCalculator())"

# 4. 清理后重试
rm -rf workspace/extract/
rm -rf workspace/signed/
rm -f workspace/tmp_*.apk
python build.py zip 3 -v
```

---

## 开发指南

### 项目结构

```
Lyra/
├── lyra/                 # 核心模块
│   ├── __init__.py
│   ├── builder.py        # 构建器
│   ├── beautify.py       # 美化管理
│   ├── combinations.py   # 组合计算
│   ├── config.py         # 配置结构
│   ├── config_loader.py  # 配置加载
│   ├── download_page.py  # 页面生成
│   └── utils.py          # 工具函数
├── scripts/
│   └── ci.py            # CI 脚本
├── config/              # 配置文件
│   ├── build.toml
│   ├── features.toml
│   └── combinations.toml
├── tests/               # 测试
│   ├── test_beautify.py
│   ├── test_config.py
│   └── test_utils.py
├── build.py             # CLI 入口
├── requirements.txt     # Python 依赖
└── BUILD.md            # 本文档
```

### 代码风格

- **PEP 8**：遵循 Python 代码规范
- **类型提示**：使用类型注解
- **文档字符串**：Google 风格
- **日志**：使用 logging 模块

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python -m pytest tests/test_combinations.py

# 带覆盖率
python -m pytest --cov=lyra tests/
```

### 添加新功能

1. **创建功能分支**

```bash
git checkout -b feature/new-feature
```

1. **实现功能**

- 添加代码到相应模块
- 编写单元测试
- 更新配置文件（如需要）

1. **测试**

```bash
# 单元测试
python -m pytest tests/

# 集成测试
python build.py zip 3 -v
```

1. **提交**

```bash
git add .
git commit -m "feat: 添加新功能"
git push origin feature/new-feature
```

### 发布流程

1. **更新版本号**

```python
# lyra/__init__.py
__version__ = "1.1.0"
```

1. **生成 Changelog**

```bash
# 查看自上次发布以来的提交
git log v1.0.0..HEAD --oneline
```

1. **创建 Tag**

```bash
git tag -a v1.1.0 -m "Release v1.1.0"
git push origin v1.1.0
```

1. **GitHub Actions 自动发布**

- Push tag 触发工作流
- 自动构建所有组合
- 创建 GitHub Release
- 上传构建产物

---

## 许可证

本项目基于 GPL-3.0 协议开源。

---

## 相关链接

- **GitHub 仓库**：<https://github.com/DoL-Lyra/Lyra>
- **下载站**：<https://dol-lyra.github.io/hub/>
- **汉化仓库**：<https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization>
- **问题反馈**：<https://github.com/DoL-Lyra/Lyra/issues>

---

## 贡献者

感谢所有为本项目做出贡献的开发者！

如有问题或建议，欢迎提交 Issue 或 Pull Request。
