# Phase 3: Dual Camera 整合

**狀態：✅ 完成**

## 目標

將兩個 camera 加入 LeRobot pipeline：
- **overhead** (外部固定視角)：固定在手臂旁邊，看全局場景
- **wrist** (eye-in-hand)：裝在手臂末端，看操作細節

## 硬體配置

| 角色 | Camera 型號 | udev Symlink | 安裝位置 |
|------|------------|-------------|---------|
| **overhead** | Logitech C270 (046d:0825) | `/dev/cam_c270` | 手臂旁邊固定架 |
| **wrist** | ARC Camera (05a3:9230) | `/dev/cam_arc` | 手臂末端 |

> udev rules：`config/99-usb-camera.rules`

```
# Logitech C270 (overhead) → /dev/cam_c270
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="0825", ATTRS{serial}=="200901010001", ATTR{index}=="0", SYMLINK+="cam_c270"

# ARC Camera (wrist) → /dev/cam_arc
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="05a3", ATTRS{idProduct}=="9230", ATTRS{serial}=="USB2.0_CAM1", ATTR{index}=="0", SYMLINK+="cam_arc"
```

安裝方式：
```bash
sudo cp config/99-usb-camera.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -la /dev/cam_*
```

## 完成項目

- [x] 確認兩個 camera 硬體正常
- [x] 建立 udev rules 固定 device path
- [x] 雙 camera teleoperate 測試
- [x] 雙 camera 錄製測試
- [x] 驗證 dataset（兩個 camera 影片皆正常）
- [x] 建立正式錄製腳本 `scripts/5_record_pick_cube.sh`
- [x] 用雙 camera dataset 完成 Diffusion Policy 訓練與 Eval

## CLI Camera 參數格式

```bash
--robot.cameras="{ overhead: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30} }"
```

## 對訓練的影響

- Camera 名稱（`overhead`、`wrist`）會成為 policy 的 observation key
- 訓練和推論時必須用**完全相同**的 camera 名稱和解析度
- 雙 camera 會增加 policy 的 input 維度，訓練時間和 GPU 記憶體需求會增加

## 備註

- fourcc 用 YUYV（預設），實測 MJPG vs YUYV 體感無差異
- camera `read_latest()` 是 non-blocking（背景執行緒），加 camera 不會增加 teleop loop 延遲
- 兩個 camera 若是同型號同 VID/PID，udev rule 需靠 serial number 或 USB port path 區分
