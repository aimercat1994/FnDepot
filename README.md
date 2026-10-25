# aimercat 的飞牛应用源

个人开发的飞牛 fnOS 应用，按 [FnDepot 外部源 V2](https://github.com/EWEDLCM/FnDepot) 规范发布，供 FnDepot 客户端添加后浏览、安装与升级。

## 添加方式

在飞牛 fnOS 中打开 **FnDepot**，进入「外部源」→「添加源」，填入本仓库地址：

```text
https://github.com/aimercat1994/FnDepot
```

也可以使用 `fnpack.json` 的直链（适合自建镜像）：

```text
https://raw.githubusercontent.com/aimercat1994/FnDepot/main/fnpack.json
```

客户端读取仓库**默认分支**根目录下的 `fnpack.json`；本仓库只依赖这个文件，目录结构可自由调整。

## 收录应用

| 应用 | 版本 | 分类 | 说明 |
| --- | --- | --- | --- |
| 无损剪辑（`videocut`） | 1.2.0 | 影音娱乐 | 视频无损切割与合并：文件管理器「打开方式」直接打开、按关键帧取区间、多段无损合并，全程流复制不重新编码 |

每位应用的详细说明见各自目录下的 `README.md`，源码在 [fnos-videocut](https://github.com/aimercat1994/fnos-videocut)。

## 仓库结构

```text
fnpack.json              # 源索引：应用元数据 + 版本 + 安装包地址/哈希
videocut/
  ICON.PNG               # 应用图标（256×256）
  Preview/1..3.png       # 详情页预览图
  README.md              # 详情页说明
  fpk/videocut_v1.2.0.fpk
scripts/
  make_source.py         # 从构建好的 .fpk 生成/更新 fnpack.json
  check_source.py        # 发布前自检（字段、分类、哈希、大小、manifest 一致性）
```

## 维护流程

发布新版本时：

```bash
python3 scripts/make_source.py /path/to/videocut.fpk   # 归档 fpk、算 sha256/size、写入 releases
python3 scripts/check_source.py                        # 自检
git add -A && git commit -m "videocut 1.2.1" && git push
```

`make_source.py` 会从 fpk 内的 `manifest` 读取版本号、简介与 changelog，所以只要 manifest 改对了，源文件不会写错。**同一版本号的 fpk 不要原地替换**——客户端会在下载后强制校验 `sha256`，同版本换包请发布新版本号。

## 说明

- 外部源中的应用由个人开发和维护，安装与使用风险请自行评估；应用本身的行为以各应用仓库的说明为准。
- 不统计下载量、评分与评论（外部源不支持这些数据）。
- 图标、预览图与 README 均为应用自身的界面截图。
