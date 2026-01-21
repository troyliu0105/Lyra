class LyraVer:
    dol_ver: str
    chs_ver: str
    date: str

def extract_vers_from_string(ver_str: str) -> LyraVer:
    """从版本字符串中提取主版本、次版本和补丁版本"""
    # tag 格式: v0.5.7.9-5.0.2a-0112
    if ver_str.startswith('v'):
        ver_str = ver_str[1:]
    parts = ver_str.split('-')
    if len(parts) >= 3:
        return LyraVer(
            dol_ver=parts[0],
            chs_ver=parts[1],
            date=parts[2]
        )
    else:
        raise ValueError(f"无法从版本字符串中提取版本信息: {ver_str}")