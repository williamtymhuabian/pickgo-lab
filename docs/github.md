# 更新 GitHub 仓库

项目已发布在 [williamtymhuabian/pickgo-lab](https://github.com/williamtymhuabian/pickgo-lab)。README、app.py 与 index.html 位于仓库根目录。已有仓库按下面的流程更新即可。

## 先同步并检查差异

```bash
git status
git fetch origin
git log --oneline --left-right HEAD...origin/main
git pull --ff-only
```

工作区有未提交修改时先检查并保存自己的修改，再同步。`--ff-only` 不能继续时说明本地和远程可能已经分叉，应先检查双方提交并处理合并，不要用强制推送覆盖远程内容。

把新版文件整合到这个已有工作区，保留已有的 `.git`、演示素材、来源说明和需要的文档。不要把 Git 凭据、Python 环境、SDK、摄像头录制或整个原始工作区加入仓库。

## 本地验证

```bash
node tests/simulation.test.cjs
node tests/camera.test.cjs
python -B tests/test_vision.py
python -B tests/test_mcp.py
node experiments/reachability-probe.cjs
```

完整视觉测试需要 requirements.txt 中的依赖。测试使用合成图、内存中的测试流和本机临时端口，不打开真实摄像头。实验仅使用独立运动学仿真实例。

## 提交与推送

```bash
git diff --stat
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "Update PickGo Lab to v0.3.0"
git push origin main
```

提交前审阅暂存内容。推送被拒绝时先 `git fetch origin` 并检查新增提交，再处理合并或变基；不要直接使用 `--force`。保留原始机器人代码的来源和许可说明，见 NOTICE.md。

`mcp.example.json` 中的绝对路径是占位示例，使用时改为自己电脑上的路径；不要把令牌写进配置或远端 URL。
