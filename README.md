# CloseLoop-Result-2

闭环评测结果仓库（续），接续 [CloseLoop-Result](https://github.com/CHAROla1/CloseLoop-Result)。因原仓库接近 GitHub 容量上限（~4.2 GB / 5 GB），自 2026-11-19 的新批次起在本仓库归档。目录结构、上传与按需拉取流程与原仓库一致，工具脚本在 `tools/`。

## 目录

```text
batches/
  <batch-id>/          # 可直接浏览的批量报告（HTML + JSON + MP4）
perframe/
  <batch-id>/          # 每帧中间结果与真值归档
tools/                 # 数据提取/转换脚本
```

## 检查和提交

```bash
git status --short
git add "batches/<batch-id>"
git diff --cached --stat
git commit -m "results: add <batch-id>"
git tag "batch/<batch-id>"

# 本机代理对大推送会 HTTP 408 超时，推送需绕过代理直连
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY git push origin main --tags
```

单批超过 ~1.8 GB 时分两次提交、分两趟推送（GitHub 单次推送包上限 ~2 GB）。

## 按需拉取某个批次

```bash
git clone --filter=blob:none --no-checkout https://github.com/CHAROla1/CloseLoop-Result-2.git
cd CloseLoop-Result-2
git sparse-checkout set batches/<batch-id>   # 换成想看的批次目录
git checkout main
```

之后 `git sparse-checkout add <目录>` 追加，`git pull` 前先拉取更新。注意 `sparse-checkout set` 只认目录路径；`batch/<batch-id>` 是 tag，用于 `git checkout <tag>` 定位快照。

## 本地浏览

```bash
cd batches/<batch-id>
python -m http.server 18765 --bind 0.0.0.0
```

浏览器打开 `http://<主机地址>:18765/`。网页通过 HTTP 加载 JSON 和视频，直接双击 `index.html` 可能无法正常读取资源。
