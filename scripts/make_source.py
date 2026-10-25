#!/usr/bin/env python3
"""从构建好的 .fpk 生成 / 更新 FnDepot 外部源的 fnpack.json。

用法：
    python3 scripts/make_source.py ../videocut/videocut.fpk

做的事：
  1. 把 fpk 复制到 <appname>/fpk/<appname>_v<version>.fpk
  2. 从 fpk 内的 manifest 读 appname / version / display_name / desc / platform / changelog
  3. 计算 sha256 与 size，写进 fnpack.json 的对应版本节点（同版本覆盖，旧版本保留）

应用级元数据（分类、图标、预览图、开发者等）在本文件顶部的 APPS 里维护。
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_JSON = os.path.join(ROOT, "fnpack.json")

CATEGORIES = {
    "影音娱乐", "系统工具", "编程开发", "AI赋能", "生活服务",
    "智能智控", "教育学习", "游戏地带", "硬件驱动",
}

SOURCE_INFO = {
    "name": "aimercat 应用源",
    "author": "aimercat",
    "homepage": "https://github.com/aimercat1994/FnDepot",
    "description": "个人开发的飞牛 fnOS 应用，当前收录：无损剪辑。",
}

# 应用级元数据；版本、简介、changelog 由 fpk 的 manifest 提供
APPS = {
    "videocut": {
        "categories": ["影音娱乐"],
        "icon_url": "./videocut/ICON.PNG",
        "preview_urls": [
            "./videocut/Preview/1.png",
            "./videocut/Preview/2.png",
            "./videocut/Preview/3.png",
        ],
        "readme_url": "./videocut/README.md",
        "bug_report_url": "https://github.com/aimercat1994/fnos-videocut/issues",
        "maintainer": "aimercat",
        "maintainer_url": "https://github.com/aimercat1994",
        "distributor": "aimercat",
        "distributor_url": "https://github.com/aimercat1994",
        "is_docker": False,
    },
}


def read_manifest(fpksrc):
    """fpk 是 tar.gz，manifest 在根目录。"""
    with tarfile.open(fpksrc, "r:gz") as tar:
        for name in tar.getnames():
            if os.path.basename(name) != "manifest" or "/" in name.strip("./"):
                continue
            raw = tar.extractfile(name).read().decode("utf-8", "replace")
            break
        else:
            raise SystemExit("fpk 里没有找到 manifest")
    out = {}
    for line in raw.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*)\s*=\s*(.+)$", line.rstrip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def first_changelog(text, version):
    """manifest 的 changelog 是 `版本 说明|版本 说明|...`，取出本版本那一条。"""
    for part in (text or "").split("|"):
        part = part.strip()
        if part.startswith(version + " "):
            out = part[len(version) + 1:].strip()
            # 客户端按纯文本展示，去掉 markdown 强调与代码标记
            return out.replace("**", "").replace("`", "").strip()
    return "更新至 %s。" % version


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    fpksrc = os.path.abspath(sys.argv[1])
    man = read_manifest(fpksrc)
    appname = man.get("appname")
    version = man.get("version")
    if not appname or not version:
        raise SystemExit("manifest 缺少 appname / version")

    meta = APPS.get(appname)
    if not meta:
        raise SystemExit("APPS 里没有登记 %s，请先在脚本里补应用级元数据" % appname)
    for cat in meta["categories"]:
        if cat not in CATEGORIES:
            raise SystemExit("分类 %s 不在允许的九个固定分类里" % cat)

    plat = man.get("platform", "all").strip() or "all"
    if plat not in ("all", "x86", "arm"):
        raise SystemExit("platform 只能是 all / x86 / arm，当前 %s" % plat)

    # 1. 归档安装包
    dest_dir = os.path.join(ROOT, appname, "fpk")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "%s_v%s.fpk" % (appname, version))
    if os.path.abspath(fpksrc) != os.path.abspath(dest):
        shutil.copy2(fpksrc, dest)

    # 2. 哈希与大小
    h = hashlib.sha256()
    with open(dest, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    size = os.path.getsize(dest)

    # 3. 合并进 fnpack.json
    if os.path.exists(SOURCE_JSON):
        with open(SOURCE_JSON, encoding="utf-8") as fh:
            doc = json.load(fh)
    else:
        doc = {"schema_version": "2", "source_info": SOURCE_INFO, "apps": {}}

    app = doc["apps"].setdefault(appname, {})
    app.update({
        "display_name": man.get("display_name", appname),
        "desc": man.get("desc", ""),
        "platform": [plat],
        "categories": meta["categories"],
        "icon_url": meta["icon_url"],
        "preview_urls": meta["preview_urls"],
        "readme_url": meta["readme_url"],
        "bug_report_url": meta["bug_report_url"],
        "maintainer": meta.get("maintainer", ""),
        "maintainer_url": meta.get("maintainer_url", ""),
        "distributor": meta.get("distributor", ""),
        "distributor_url": meta.get("distributor_url", ""),
        "run_as": "package",
        "install_type": man.get("install_type", "").strip(),
        "is_docker": meta["is_docker"],
        "service_port": man.get("service_port", "").strip(),
    })

    changelog = first_changelog(man.get("changelog", ""), version)
    releases = app.setdefault("releases", {})
    old = releases.get(version, {})
    old_pkg = (old.get("packages") or {}).get("all") or {}
    branch = "all" if plat == "all" else plat
    package = {
        "download_url": "./%s/fpk/%s_v%s.fpk" % (appname, appname, version),
        "sha256": h.hexdigest(),
        "size": size,
    }
    # 同一个版本换了安装包（哈希变了）才刷新更新时间，否则保留首次发布的时间
    updated_at = old.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    if old_pkg.get("sha256") and old_pkg["sha256"] != package["sha256"]:
        updated_at = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    rel = {"changelog": changelog, "updated_at": updated_at}
    if man.get("os_min_version"):
        rel["os_min_version"] = man["os_min_version"].strip()
    if man.get("os_max_version"):
        rel["os_max_version"] = man["os_max_version"].strip()
    rel["packages"] = dict(old.get("packages") or {}, **{branch: package})
    releases[version] = rel

    with open(SOURCE_JSON, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("appname   :", appname)
    print("version   :", version)
    print("fpk       :", os.path.relpath(dest, ROOT), "(%d bytes)" % size)
    print("sha256    :", h.hexdigest())
    print("categorized:", " / ".join(meta["categories"]))
    print("fnpack.json 已更新:", os.path.relpath(SOURCE_JSON, ROOT))


if __name__ == "__main__":
    main()
