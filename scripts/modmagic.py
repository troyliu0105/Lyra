import json
import re
import sys
import base64
from pathlib import Path
from typing import List, Literal, Dict
import zipfile
from io import BytesIO


def load_file_as_base64(file_path: str) -> str:
    """将文件转换为 base64 字符串"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_boot_json_from_base64_zip(base64_data: str) -> Dict:
    """从 base64 编码的 zip 中提取 boot.json 信息"""
    try:
        # 解码 base64
        zip_bytes = base64.b64decode(base64_data)

        # 从字节创建 zip 文件对象
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            # 查找 boot.json
            boot_json_files = [f for f in zf.namelist() if f.endswith("boot.json")]

            if not boot_json_files:
                return {
                    "name": "Unknown",
                    "version": "Unknown",
                    "error": "boot.json not found",
                }

            boot_json_path = boot_json_files[0]

            # 读取并解析 boot.json
            with zf.open(boot_json_path) as boot_file:
                boot_data = json.load(boot_file)
                return {
                    "name": boot_data.get("name", "Unknown"),
                    "version": boot_data.get("version", "Unknown"),
                    "author": boot_data.get("author", ""),
                    "description": boot_data.get("description", ""),
                }
    except Exception as e:
        return {"name": "Unknown", "version": "Unknown", "error": str(e)}


def extract_mod_list(html_content: str) -> List[str]:
    """从 HTML 文件中提取 modDataValueZipList 数组"""
    pattern = r"window\.modDataValueZipList\s*=\s*(\[.*?\]);"
    match = re.search(pattern, html_content, re.DOTALL)

    if not match:
        raise ValueError("modDataValueZipList not found in HTML file")

    # 使用 json 解析 base64 数组
    try:
        mod_list = json.loads(match.group(1))
        return mod_list
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse modDataValueZipList: {e}")


def add_mods_to_html(
    html_mod_path: str, mod_paths: List[str], position: Literal["start", "end"] = "end"
):
    """向已有的 .mod.html 文件中添加新 Mod"""

    # 读取 HTML 文件
    with open(html_mod_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 提取现有的 modDataValueZipList
    existing_list = extract_mod_list(html_content)
    print(f"Found {len(existing_list)} existing mod(s)")

    # 加载新的 Mod 文件
    new_mod_base64_list = []
    for mod_path in mod_paths:
        if not Path(mod_path).exists():
            raise FileNotFoundError(f"Mod file not found: {mod_path}")
        base64_data = load_file_as_base64(mod_path)
        new_mod_base64_list.append(base64_data)
        print(f"Loaded mod: {mod_path}")

    # 合并数组
    if position == "start":
        new_list = new_mod_base64_list + existing_list
    else:
        new_list = existing_list + new_mod_base64_list

    # 替换 modDataValueZipList
    new_content = re.sub(
        r"window\.modDataValueZipList\s*=\s*\[.*?\];",
        f"window.modDataValueZipList = {json.dumps(new_list)};",
        html_content,
        flags=re.DOTALL,
    )

    # 写回文件
    with open(html_mod_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Successfully added {len(mod_paths)} mod(s) to {html_mod_path}")


def reorder_mods(html_mod_path: str, new_order: List[int]):
    """重新排列 HTML 文件中的 Mod 顺序"""

    # 读取 HTML 文件
    with open(html_mod_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 提取现有的 modDataValueZipList
    existing_list = extract_mod_list(html_content)

    # 验证索引有效性
    if not all(0 <= idx < len(existing_list) for idx in new_order):
        raise ValueError(
            f"Invalid index in new_order. Valid range: 0-{len(existing_list) - 1}"
        )

    # 按新顺序重新排列
    reordered_list = [existing_list[i] for i in new_order]

    # 替换 modDataValueZipList
    new_content = re.sub(
        r"window\.modDataValueZipList\s*=\s*\[.*?\];",
        f"window.modDataValueZipList = {json.dumps(reordered_list)};",
        html_content,
        flags=re.DOTALL,
    )

    # 写回文件
    with open(html_mod_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Successfully reordered mods in {html_mod_path}")
    print(f"New order: {new_order}")


def remove_mods(html_mod_path: str, indices: List[int]):
    """删除指定索引的 Mod"""

    # 读取 HTML 文件
    with open(html_mod_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 提取现有的 modDataValueZipList
    existing_list = extract_mod_list(html_content)

    # 验证索引有效性
    if not all(0 <= idx < len(existing_list) for idx in indices):
        raise ValueError(f"Invalid index. Valid range: 0-{len(existing_list) - 1}")

    # 删除指定索引的 Mod
    new_list = [mod for i, mod in enumerate(existing_list) if i not in indices]

    # 替换 modDataValueZipList
    new_content = re.sub(
        r"window\.modDataValueZipList\s*=\s*\[.*?\];",
        f"window.modDataValueZipList = {json.dumps(new_list)};",
        html_content,
        flags=re.DOTALL,
    )

    # 写回文件
    with open(html_mod_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Successfully removed {len(indices)} mod(s) from {html_mod_path}")


def replace_mod_by_id(html_mod_path: str, mod_id: int, mod_path: str):
    """覆盖指定索引位置的 Mod"""

    # 读取 HTML 文件
    with open(html_mod_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 提取现有的 modDataValueZipList
    existing_list = extract_mod_list(html_content)

    # 验证索引有效性
    if not (0 <= mod_id < len(existing_list)):
        raise ValueError(f"Invalid mod ID. Valid range: 0-{len(existing_list) - 1}")

    # 检查新 Mod 文件
    if not Path(mod_path).exists():
        raise FileNotFoundError(f"Mod file not found: {mod_path}")

    # 加载新 Mod 并转换为 base64
    new_base64_data = load_file_as_base64(mod_path)

    # 获取旧 Mod 信息
    old_boot_info = extract_boot_json_from_base64_zip(existing_list[mod_id])
    old_name = old_boot_info.get("name", "Unknown")

    # 获取新 Mod 信息
    new_boot_info = extract_boot_json_from_base64_zip(new_base64_data)
    new_name = new_boot_info.get("name", "Unknown")
    new_version = new_boot_info.get("version", "Unknown")

    # 替换指定位置的 Mod
    existing_list[mod_id] = new_base64_data

    # 替换 modDataValueZipList
    new_content = re.sub(
        r"window\.modDataValueZipList\s*=\s*\[.*?\];",
        f"window.modDataValueZipList = {json.dumps(existing_list)};",
        html_content,
        flags=re.DOTALL,
    )

    # 写回文件
    with open(html_mod_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Successfully replaced mod at ID {mod_id}")
    print(f"  Old: [{old_name}]")
    print(f"  New: [{new_name}] v{new_version}")


def list_mods(html_mod_path: str):
    """列出 HTML 文件中的所有 Mod（显示详细信息）"""

    # 读取 HTML 文件
    with open(html_mod_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 提取现有的 modDataValueZipList
    mod_list = extract_mod_list(html_content)

    print(f"\n{'=' * 80}")
    print(f"Total mods: {len(mod_list)}")
    print(f"{'=' * 80}\n")

    for i, mod_base64 in enumerate(mod_list):
        boot_info = extract_boot_json_from_base64_zip(mod_base64)
        size_kb = len(mod_base64) / 1024

        print(f"[{i}] {boot_info.get('name', 'Unknown')}")
        print(f"    Version: {boot_info.get('version', 'Unknown')}")
        print(f"    Size: {size_kb:.2f} KB")
        if boot_info.get("author"):
            print(f"    Author: {boot_info.get('author')}")
        if boot_info.get("description"):
            print(f"    Description: {boot_info.get('description')}")
        if boot_info.get("error"):
            print(f"    ⚠️  Error: {boot_info.get('error')}")
        print()


def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "add":
            if len(sys.argv) < 4:
                print(
                    "Usage: python modifyModList.py add <html.mod.html> <mod1.zip> [<mod2.zip> ...] [--start|--end]"
                )
                sys.exit(1)

            html_path = sys.argv[2]
            mod_paths = sys.argv[3:]

            position = "end"
            if "--start" in mod_paths:
                position = "start"
                mod_paths.remove("--start")
            elif "--end" in mod_paths:
                mod_paths.remove("--end")

            add_mods_to_html(html_path, mod_paths, position)

        elif command == "reorder":
            if len(sys.argv) < 4:
                print(
                    "Usage: python modifyModList.py reorder <html.mod.html> <index1> <index2> ..."
                )
                sys.exit(1)

            html_path = sys.argv[2]
            new_order = [int(x) for x in sys.argv[3:]]
            reorder_mods(html_path, new_order)

        elif command == "remove":
            if len(sys.argv) < 4:
                print(
                    "Usage: python modifyModList.py remove <html.mod.html> <index1> [<index2> ...]"
                )
                sys.exit(1)

            html_path = sys.argv[2]
            indices = [int(x) for x in sys.argv[3:]]
            remove_mods(html_path, indices)

        elif command == "replace":
            if len(sys.argv) < 5:
                print(
                    "Usage: python modifyModList.py replace <html.mod.html> <mod_id> <new_mod.zip>"
                )
                sys.exit(1)

            html_path = sys.argv[2]
            mod_id = int(sys.argv[3])
            mod_path = sys.argv[4]
            replace_mod_by_id(html_path, mod_id, mod_path)

        elif command == "list":
            if len(sys.argv) < 3:
                print("Usage: python modifyModList.py list <html.mod.html>")
                sys.exit(1)

            html_path = sys.argv[2]
            list_mods(html_path)

        else:
            print_help()
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def print_help():
    print(
        """
modifyModList.py - 修改已有的 .mod.html 文件中的 Mod 列表

用法:
  python modifyModList.py add <html.mod.html> <mod1.zip> [<mod2.zip> ...] [--start|--end]
    添加新 Mod 到文件末尾（--end）或开头（--start），默认为末尾
  
  python modifyModList.py replace <html.mod.html> <mod_id> <new_mod.zip>
    覆盖指定 ID 的 Mod
  
  python modifyModList.py reorder <html.mod.html> <index1> <index2> ...
    按新顺序重新排列 Mod
  
  python modifyModList.py remove <html.mod.html> <index1> [<index2> ...]
    删除指定索引的 Mod
  
  python modifyModList.py list <html.mod.html>
    列出所有 Mod 及其详细信息

示例:
  python modifyModList.py list test.html.mod.html
  python modifyModList.py add test.html.mod.html mod1.zip mod2.zip --end
  python modifyModList.py replace test.html.mod.html 0 new_mod.zip
  python modifyModList.py reorder test.html.mod.html 2 0 1
  python modifyModList.py remove test.html.mod.html 0 2
"""
    )


if __name__ == "__main__":
    main()
