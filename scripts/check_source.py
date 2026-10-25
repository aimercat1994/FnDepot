#!/usr/bin/env python3
"""按 FnDepot 外部源 V2 规范自检 fnpack.json（发布前跑一遍）。

用法：
    python3 scripts/check_source.py

退出码 0 = 通过；非 0 = 有问题，逐条打印。
"""
import hashlib
import json
import os
import re
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_JSON = os.path.join(ROOT, "fnpack.json")

CATEGORIES = {
    "影音娱乐", "系统工具", "编程开发", "AI赋能", "生活服务",
    "智能智控", "教育学习", "游戏地带", "硬件驱动",
}
PLATFORMS = {"all", "x86", "arm"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

problems = []
notes = []


def bad(msg):
    problems.append(msg)


def resolve(url, base_dir):
    """相对 URL 按主 JSON 所在目录解析成仓库内路径。"""
    if re.match(r"^https?://", url):
        return None
    if url.startswith("./"):
        url = url[2:]
    return os.path.normpath(os.path.join(base_dir, url))


def check_file(url, base_dir, label, max_bytes=None):
    path = resolve(url, base_dir)
    if path is None:
        notes.append("%s 使用绝对 URL，跳过本地检查：%s" % (label, url))
        return None
    if not os.path.isfile(path):
        bad("%s 指向的文件不存在：%s" % (label, url))
        return None
    size = os.path.getsize(path)
    if max_bytes and size > max_bytes:
        bad("%s 体积 %d 字节，超过建议上限 %d" % (label, size, max_bytes))
    return path


def fpk_manifest(path):
    with tarfile.open(path, "r:gz") as tar:
        for name in tar.getnames():
            if os.path.basename(name) == "manifest" and "/" not in name.strip("./"):
                raw = tar.extractfile(name).read().decode("utf-8", "replace")
                break
        else:
            raise ValueError("fpk 内没有 manifest")
    out = {}
    for line in raw.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*)\s*=\s*(.+)$", line.rstrip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def main():
    if not os.path.isfile(SOURCE_JSON):
        print("找不到 fnpack.json")
        return 1
    try:
        raw = open(SOURCE_JSON, encoding="utf-8").read()
        doc = json.loads(raw)
    except Exception as exc:
        print("JSON 解析失败：", exc)
        return 1

    if doc.get("schema_version") != "2":
        bad("schema_version 必须是字符串 \"2\"，当前 %r" % doc.get("schema_version"))

    si = doc.get("source_info") or {}
    if not isinstance(si, dict):
        bad("source_info 必须是对象")
    else:
        for f in ("name", "author"):
            if not (si.get(f) or "").strip():
                bad("source_info.%s 不能为空" % f)
        if si.get("id"):
            notes.append("source_info.id 不参与身份判断，V2 不需要该字段")

    apps = doc.get("apps")
    if not isinstance(apps, dict) or not apps:
        bad("apps 必须是非空对象")
        apps = {}

    if len(raw.encode("utf-8")) > 2 * 1024 * 1024:
        bad("主源 JSON 超过 2MB 上限")

    for name, app in apps.items():
        if not NAME_RE.match(name):
            bad("应用键 %s 不符合命名规则（字母数字点下划线短横线，且以字母数字开头）" % name)
        if not isinstance(app, dict):
            bad("应用 %s 必须是对象" % name)
            continue

        for f in ("display_name", "desc", "icon_url", "run_as", "install_type", "is_docker"):
            if f not in app:
                bad("%s 缺少必填字段 %s" % (name, f))
        if not str(app.get("display_name") or "").strip():
            bad("%s.display_name 不能为空" % name)
        if app.get("run_as") not in ("package", "root"):
            bad("%s.run_as 只能是 package / root，当前 %r" % (name, app.get("run_as")))
        if not isinstance(app.get("is_docker"), bool):
            bad("%s.is_docker 必须是布尔值" % name)
        if not isinstance(app.get("install_type"), str):
            bad("%s.install_type 必须是字符串（空串=存储空间）" % name)

        cats = app.get("categories") or []
        if not cats:
            bad("%s.categories 至少一个" % name)
        if len(cats) > 2:
            bad("%s.categories 最多两个" % name)
        for c in cats:
            if c not in CATEGORIES:
                bad("%s.categories 含非法分类 %r（只能是九个固定分类）" % (name, c))

        plats = app.get("platform")
        plats = [plats] if isinstance(plats, str) else (plats or [])
        if not plats:
            bad("%s.platform 必填" % name)
        for p in plats:
            if p not in PLATFORMS:
                bad("%s.platform 含非法值 %r" % (name, p))

        if app.get("icon_url"):
            check_file(app["icon_url"], ROOT, "%s.icon_url" % name, 500 * 1024)
        if app.get("readme_url"):
            check_file(app["readme_url"], ROOT, "%s.readme_url" % name, 1024 * 1024)
        for i, u in enumerate(app.get("preview_urls") or []):
            check_file(u, ROOT, "%s.preview_urls[%d]" % (name, i), 2 * 1024 * 1024)
        if len(app.get("preview_urls") or []) > 8:
            bad("%s.preview_urls 超过 8 张，客户端只读前 8 张" % name)

        releases = app.get("releases")
        if not isinstance(releases, dict) or not releases:
            bad("%s.releases 必须是非空对象" % name)
            continue
        if len(releases) > 100:
            bad("%s 版本数超过 100" % name)

        for ver, rel in releases.items():
            tag = "%s@%s" % (name, ver)
            if not re.match(r"^\d", ver):
                bad("%s 版本号必须以数字开头" % tag)
            if ver.lower() in ("latest",):
                bad("%s 版本号不能是 latest" % tag)
            if not isinstance(rel, dict):
                bad("%s 版本节点必须是对象" % tag)
                continue
            if rel.get("os_min_version") is not None and not isinstance(rel["os_min_version"], str):
                bad("%s.os_min_version 必须是字符串" % tag)
            if not isinstance(rel.get("changelog", ""), str):
                bad("%s.changelog 必须是字符串" % tag)

            packages = rel.get("packages")
            if not isinstance(packages, dict) or not packages:
                bad("%s.packages 必须是非空对象" % tag)
                continue
            for arch, pkg in packages.items():
                ptag = "%s/%s" % (tag, arch)
                if arch not in PLATFORMS:
                    bad("%s 架构键非法（只能是 all / x86 / arm）" % ptag)
                if not isinstance(pkg, dict):
                    bad("%s 安装包节点必须是对象" % ptag)
                    continue
                url = pkg.get("download_url")
                if not url:
                    bad("%s 缺少 download_url" % ptag)
                    continue
                path = check_file(url, ROOT, "%s.download_url" % ptag)
                if not path:
                    continue
                if not isinstance(pkg.get("size"), int) or pkg["size"] < 0:
                    bad("%s.size 必须是非负整数（字节）" % ptag)
                elif pkg["size"] != os.path.getsize(path):
                    bad("%s.size=%s 与实际文件 %d 字节不符"
                        % (ptag, pkg["size"], os.path.getsize(path)))
                sha = (pkg.get("sha256") or "").lower()
                if not re.match(r"^[0-9a-f]{64}$", sha):
                    bad("%s.sha256 必须是 64 位十六进制" % ptag)
                else:
                    h = hashlib.sha256()
                    with open(path, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            h.update(chunk)
                    if h.hexdigest() != sha:
                        bad("%s.sha256 与文件实际哈希不符" % ptag)
                # fpk 与源文件一致性
                try:
                    man = fpk_manifest(path)
                except Exception as exc:
                    bad("%s 无法读取 fpk：%s" % (ptag, exc))
                    continue
                if man.get("appname") != name:
                    bad("%s 的 fpk appname=%r 与源键不一致" % (ptag, man.get("appname")))
                if man.get("version") != ver:
                    bad("%s 的 fpk version=%r 与版本键不一致" % (ptag, man.get("version")))
                fplat = man.get("platform", "all")
                if arch != "all" and fplat not in ("all", arch):
                    bad("%s 的 fpk platform=%r 与架构分支 %s 不符" % (ptag, fplat, arch))

    print("source_info:", si.get("name"), "/", si.get("author"))
    print("apps       :", ", ".join(apps.keys()) or "—")
    for n in notes:
        print("  note:", n)
    if problems:
        print("\nPROBLEMS (%d):" % len(problems))
        for p in problems:
            print("  -", p)
        return 1
    print("\nOK: 符合 FnDepot V2 规范")
    return 0


if __name__ == "__main__":
    sys.exit(main())
