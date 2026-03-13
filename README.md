# piper-lerobot

Piper 機械手臂 + LeRobot framework 的 imitation learning 專案。

包含 LeRobot plugin（Piper follower、ROBOTIS leader、keyboard teleoperator）、資料收集/訓練/評估腳本，以及相關工具。

## 目錄結構

```
plugins/          LeRobot plugins (pip install -e)
scripts/          操作腳本（teleop、record、train、eval）
tools/            維護與 debug 工具
config/           udev rules 等硬體設定
doc/              完整文件（架構、各 phase 記錄、踩坑筆記）
```

## 快速開始

詳見 [doc/00-infra-overview.md](doc/00-infra-overview.md)。
