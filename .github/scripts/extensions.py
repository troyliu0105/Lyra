#!/usr/bin/env python3
"""下载并兼容性校验注入到 DoL 页面的 ModLoader 扩展。

流程：
1. 从已解压的上游 HTML 读取 ModLoader 版本与内置 mod 清单（window.modDataValueZipList）。
2. 按声明下载各扩展的最新匹配 release asset。
3. 读取每个扩展的 boot.json，按 ModLoader 的 InfiniteSemVer 规则校验
   dependenceInfo / addonPlugin 是否被「内置 mod + 已接受扩展」满足。
4. 不兼容的扩展移到临时目录，只有兼容的 *.mod.zip 留在 extensions/ 供注入步骤使用。

退出码 0 表示完成（不兼容的扩展只告警）；下载/解析失败直接抛错，避免静默漏装。
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

BUILD_DIR = Path(os.environ.get("DOWNLOAD_RELEASE_TEMP_PATH", "."))
HTML_PATH = BUILD_DIR / "normal" / "dol.html"
EXT_DIR = BUILD_DIR / "extensions"
REJECT_DIR = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "rejected-extensions"
SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY", "")

# order 决定注入顺序（文件名前缀）：扩展在 HTML 内置 mod 之后按此顺序加载。
# dep_only=True 的条目只在被其它扩展依赖时才保留。
EXTENSIONS = [
    {
        "key": "maplebirch",
        "order": 10,
        "repo": "MaplebirchLeaf/SCML-DOL-maplebirchFramework",
        "asset": r"^maplebirch-{dol_ver}-v[\d.]+\.mod\.zip$",
    },
    {
        "key": "guidetome",
        "order": 11,
        "url": "https://github.com/Ayndpa/DOL-GuideToMe/releases/download/1.1.0/GuideToMe.zip",
    },
    {
        "key": "dolsims",
        "order": 12,
        "url": "https://github.com/MissedHeart/Degrees-of-Lewdity-DolSims/releases/download/v0.8.1.6.2/DoLSims.mod.zip",
    },
    {
        "key": "stonefreehost",
        "order": 20,
        "repo": "102326/DoL-Game-UI",
        "asset": r"^StoneFreeHost-.*\.mod\.zip$",
        "dep_only": True,
    },
    {
        "key": "dolgui",
        "order": 21,
        "repo": "102326/DoL-Game-UI",
        "asset": r"^DoLGameUI-.*\.mod\.zip$",
    },
    {
        "key": "doli",
        "order": 30,
        "repo": "ArsNativa/Degrees-of-Lewdity-Intelligence",
        "asset": r"^DOLI\.mod\.zip$",
    },
    {
        "key": "exhibitionism",
        "order": 31,
        "repo": "ANLINSTUDIO/Degrees-of-Lewdity-MyExhibitionismExpansion",
        "asset": r".*DolMod\.zip$",
        "allow_prerelease": True,
    },
    {
        "key": "fertility",
        "order": 32,
        "repo": "Liliths-Legacy/DOL-FertilityExpansion-MOD",
        # Visual 变体带 36MB 图片；在线版用 Lite，避免页面无谓膨胀。
        "asset": r".*-Lite\.mod\.zip$",
    },
]


# ---------------------------------------------------------------------------
# InfiniteSemVer（移植 Lyoko-Jeremie/sugarcube-2-ModLoader 的实现）
# ---------------------------------------------------------------------------

OPERATORS = (">=", "<=", ">", "<", "=", "^")


def parse_version(text: str):
    text = text.strip()
    op = None
    for candidate in OPERATORS:
        if text.startswith(candidate):
            op, text = candidate, text[len(candidate):]
            break
    text = text.strip()
    if not text or not text[0].isdigit():
        return {"version": [], "pre": None, "build": None, "op": op}
    sp1 = text.find("-")
    sp1 = len(text) if sp1 == -1 else sp1
    sp2 = text.find("+")
    sp2 = len(text) if sp2 == -1 else sp2
    sp = min(sp1, sp2)
    parts = text[:sp].split(".")
    numbers = []
    for part in parts:
        if not part.isdigit():
            break
        numbers.append(int(part))
    return {
        "version": numbers or [0],
        "pre": text[sp1 + 1:sp2] if sp1 < sp2 else None,
        "build": text[sp2 + 1:] if sp2 < len(text) else None,
        "op": op,
    }


def compare_versions(a, b, ignore_postfix=False):
    for index in range(max(len(a["version"]), len(b["version"]))):
        av = a["version"][index] if index < len(a["version"]) else 0
        bv = b["version"][index] if index < len(b["version"]) else 0
        if av != bv:
            return av - bv
    if ignore_postfix:
        return 0
    if a["pre"] and b["pre"]:
        return (a["pre"] > b["pre"]) - (a["pre"] < b["pre"])
    if a["pre"]:
        return -1
    if b["pre"]:
        return 1
    if a["build"] and b["build"]:
        return (a["build"] > b["build"]) - (a["build"] < b["build"])
    if a["build"]:
        return -1
    if b["build"]:
        return 1
    return 0


def parse_range(text: str):
    sets = []
    for chunk in re.split(r"\s*\|\|\s*", text.strip()):
        boundaries = re.split(r"\s*&&\s*", chunk)
        if not 0 < len(boundaries) <= 2:
            continue
        lower = upper = None
        valid = True
        for boundary in boundaries:
            item = parse_version(boundary)
            op = item["op"]
            if not item["version"]:
                valid = False
                break
            if op in (">", ">="):
                if lower:
                    valid = False
                    break
                lower = (item, op)
            elif op in ("<", "<="):
                if upper:
                    valid = False
                    break
                upper = (item, op)
            elif op == "^":
                if lower or upper:
                    valid = False
                    break
                lower = (item, ">=")
                major = item["version"][0]
                if major == 0:
                    minor = item["version"][1] + 1 if len(item["version"]) >= 2 else 1
                    upper = ({"version": [0, minor], "pre": None, "build": None}, "<")
                else:
                    upper = ({"version": [major + 1], "pre": None, "build": None}, "<")
            else:  # "=" 或未写运算符：精确匹配
                if lower or upper:
                    valid = False
                    break
                lower = (item, ">=")
                upper = (item, "<=")
        if valid:
            sets.append((lower, upper))
    return sets


def satisfies(version_text: str, range_text: str, ignore_postfix=False):
    version = parse_version(version_text)
    for lower, upper in parse_range(range_text):
        ok = True
        if lower:
            diff = compare_versions(version, lower[0], ignore_postfix)
            if (lower[1] == ">" and diff <= 0) or (lower[1] == ">=" and diff < 0):
                ok = False
        if ok and upper:
            diff = compare_versions(version, upper[0], ignore_postfix)
            if (upper[1] == "<" and diff >= 0) or (upper[1] == "<=" and diff > 0):
                ok = False
        if ok:
            return True
    return False


# ---------------------------------------------------------------------------
# 读取上游 HTML 的 mod 清单
# ---------------------------------------------------------------------------


def read_zip_boot(blob_or_path):
    source = io.BytesIO(blob_or_path) if isinstance(blob_or_path, bytes) else blob_or_path
    with zipfile.ZipFile(source) as archive:
        candidates = [n for n in archive.namelist() if n == "boot.json" or n.endswith("/boot.json")]
        if not candidates:
            raise ValueError(f"boot.json not found in {blob_or_path}")
        return json.loads(archive.read(candidates[0]))


def read_base_registry(path: Path = HTML_PATH):
    html = path.read_text(encoding="utf-8", errors="replace")
    marker = "window.modDataValueZipList = "
    index = html.find(marker)
    if index == -1:
        raise SystemExit(f"modDataValueZipList not found in {path}")
    array, _ = json.JSONDecoder().raw_decode(html[html.find("[", index):])
    registry = {}
    for entry in array:
        boot = read_zip_boot(base64.b64decode(entry))
        name = boot.get("name")
        if name:
            registry[name] = str(boot.get("version", ""))
    # 上游 HTML 里 ModUtils 的源码以转义换行（字面 \n）嵌入 JS 字符串，需同时接受两种形式。
    match = re.search(r"get version\s*\(\s*\)\s*(?:\\n|\s)*\{\s*(?:\\n|\s)*return\s*'([^']+)'", html)
    return registry, (match.group(1) if match else None)


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


def api_get(path: str):
    request = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "lyra-extensions",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == 3:
                raise
            print(f"::warning::GitHub API 请求失败（{error}），重试 {attempt}/3")
            time.sleep(3 * attempt)


_RELEASE_CACHE = {}


def list_releases(repo: str):
    if repo in _RELEASE_CACHE:
        return _RELEASE_CACHE[repo]
    releases = []
    for page in range(1, 4):
        batch = api_get(f"/repos/{repo}/releases?per_page=100&page={page}")
        releases.extend(batch)
        if len(batch) < 100:
            break
    ordered = sorted(
        (r for r in releases if not r.get("draft")),
        key=lambda r: r.get("published_at") or "",
        reverse=True,
    )
    _RELEASE_CACHE[repo] = ordered
    return ordered


def download(url: str, dest: Path):
    request = urllib.request.Request(url, headers={"User-Agent": "lyra-extensions"})
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=300) as response, dest.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            return
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == 3:
                raise
            print(f"::warning::下载失败（{error}），重试 {attempt}/3: {url}")
            time.sleep(3 * attempt)


def resolve_spec(spec, dol_ver):
    if "url" in spec:
        return {"url": spec["url"], "name": "pinned", "updated_at": "", "digest": spec["url"]}
    pattern = re.compile(spec["asset"].format(dol_ver=re.escape(dol_ver)))
    for release in list_releases(spec["repo"]):
        if release.get("prerelease") and not spec.get("allow_prerelease"):
            continue
        for asset in release.get("assets", []):
            if pattern.search(asset["name"]):
                return {
                    "url": asset["browser_download_url"],
                    "name": asset["name"],
                    "updated_at": asset.get("updated_at") or "",
                    "digest": asset.get("digest") or "",
                }
    return None


def manifest(dol_ver):
    """只解析 asset 身份（不下载），供 precheck 指纹使用。"""
    entries = []
    for spec in EXTENSIONS:
        resolved = resolve_spec(spec, dol_ver)
        entries.append(
            {
                "key": spec["key"],
                "asset": resolved["name"] if resolved else "missing",
                "updated_at": resolved["updated_at"] if resolved else "",
                "digest": resolved["digest"] if resolved else "",
            }
        )
    return entries


# ---------------------------------------------------------------------------
# 兼容性判定
# ---------------------------------------------------------------------------


def dependency_problem(boot, registry, dol_ver, loader_version):
    for dep in boot.get("dependenceInfo") or []:
        name = dep.get("modName") or ""
        requirement = dep.get("version") or ""
        if name == "GameVersion":
            if not satisfies(dol_ver, requirement, ignore_postfix=True):
                return f"GameVersion {requirement} 不满足 {dol_ver}"
            continue
        if name == "ModLoader":
            if loader_version and not satisfies(loader_version, requirement):
                return f"ModLoader {requirement} 不满足 {loader_version}"
            continue
        actual = registry.get(name)
        if actual is None:
            return f"缺少依赖 {name} ({requirement})"
        if not satisfies(actual, requirement):
            return f"{name} {actual} 不满足 {requirement}"
    for addon in boot.get("addonPlugin") or []:
        host = addon.get("modName")
        if host and host not in registry:
            return f"缺少 addon 宿主 {host}"
    return None


def main():
    dol_ver = os.environ.get("dol_ver") or os.environ.get("DOL_VER")
    if not dol_ver:
        raise SystemExit("dol_ver is not set")

    base_registry, loader_version = read_base_registry(HTML_PATH)
    registries = [("normal", base_registry)]
    polyfill_html = BUILD_DIR / "polyfill" / "dol-polyfill.html"
    if polyfill_html.exists():
        registries.append(("polyfill", read_base_registry(polyfill_html)[0]))
    base_count = len(base_registry)
    print(f"base mods: {base_count}, ModLoader: {loader_version or 'unknown'}, tracks: {[t for t, _ in registries]}")
    if not loader_version:
        print("::warning::未能从 HTML 解析 ModLoader 版本，跳过 ModLoader 版本约束")

    EXT_DIR.mkdir(parents=True, exist_ok=True)
    REJECT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = []
    for spec in EXTENSIONS:
        resolved = resolve_spec(spec, dol_ver)
        dest = EXT_DIR / f"{spec['order']:02d}-{spec['key']}.mod.zip"
        if not resolved:
            # asset 缺失按“该扩展不兼容当前版本”处理，不阻断整个站点更新。
            candidates.append(
                {
                    "spec": spec,
                    "path": None,
                    "boot": {},
                    "name": spec["key"],
                    "version": "?",
                    "status": "skip",
                    "reason": f"无匹配 release asset（dol_ver={dol_ver}）",
                }
            )
            continue
        download(resolved["url"], dest)
        boot = read_zip_boot(dest)
        name, version = boot.get("name"), str(boot.get("version", ""))
        if not name:
            raise SystemExit(f"{spec['key']}: boot.json 缺少 name")
        candidates.append(
            {
                "spec": spec,
                "path": dest,
                "boot": boot,
                "name": name,
                "version": version,
                "status": "pending",
                "reason": "",
                "note": ""
                if any((d.get("modName") == "GameVersion") for d in boot.get("dependenceInfo") or [])
                else "未声明 GameVersion（无法校验）",
            }
        )

    # 迭代接受：新增扩展也可以满足其他扩展的依赖（如 StoneFreeHost → DoLGameUI）。
    changed = True
    while changed:
        changed = False
        for candidate in candidates:
            if candidate["status"] != "pending":
                continue
            if any(candidate["name"] in registry for _, registry in registries):
                candidate.update(status="skip", reason=f"已内置 {candidate['name']}")
                continue
            problem = None
            for label, registry in registries:
                problem = dependency_problem(candidate["boot"], registry, dol_ver, loader_version)
                if problem:
                    problem = f"[{label}] {problem}"
                    break
            if problem:
                candidate["reason"] = problem
                continue
            for _, registry in registries:
                registry[candidate["name"]] = candidate["version"]
            candidate.update(status="accepted", reason="")
            changed = True

    # 依赖闭包：未被任何保留扩展需要的 dep_only 条目移除。
    accepted = [c for c in candidates if c["status"] == "accepted"]
    needed = {c["name"] for c in accepted if not c["spec"].get("dep_only")}
    grew = True
    while grew:
        grew = False
        for candidate in accepted:
            if candidate["name"] not in needed:
                continue
            requires = {d.get("modName") for d in candidate["boot"].get("dependenceInfo") or []}
            requires |= {a.get("modName") for a in candidate["boot"].get("addonPlugin") or []}
            for name in requires:
                if name not in needed and any(c["name"] == name for c in accepted):
                    needed.add(name)
                    grew = True

    for candidate in accepted:
        if candidate["name"] not in needed:
            candidate.update(status="skip", reason="依赖方未保留")

    rejected = [c for c in candidates if c["status"] != "accepted"]
    for candidate in rejected:
        if candidate["path"] and candidate["path"].exists():
            shutil.move(str(candidate["path"]), str(REJECT_DIR / candidate["path"].name))

    # 报告
    lines = [
        "### Extension compatibility",
        "",
        f"- DoL: `{dol_ver}`, ModLoader: `{loader_version or 'unknown'}`, base mods: {base_count}",
        "",
        "| mod | version | 结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for candidate in candidates:
        result = "注入" if candidate["status"] == "accepted" else "跳过"
        detail = candidate["reason"] or candidate.get("note") or "-"
        lines.append(f"| {candidate['name']} | {candidate['version']} | {result} | {detail} |")
    report = "\n".join(lines)
    print(report)
    if SUMMARY:
        with open(SUMMARY, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    for candidate in rejected:
        if candidate["status"] == "skip" and candidate["reason"].startswith(("已内置", "依赖方")):
            continue
        print(f"::warning::{candidate['name']} {candidate['version']} 不兼容：{candidate['reason']}")

    accepted_count = sum(1 for c in candidates if c["status"] == "accepted")
    print(f"accepted: {accepted_count} / {len(candidates)}")


if __name__ == "__main__":
    if "--fingerprint" in sys.argv[1:]:
        fingerprint_dol_ver = os.environ.get("DOL_VER") or os.environ.get("dol_ver")
        if not fingerprint_dol_ver:
            raise SystemExit("DOL_VER is not set")
        print(json.dumps(manifest(fingerprint_dol_ver), ensure_ascii=False, sort_keys=True, indent=2))
    else:
        sys.exit(main())
