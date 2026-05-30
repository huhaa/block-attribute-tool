# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 运行

```bash
C:\Users\DHB_HOME\opense\Scripts\python.exe main.py
```

安装依赖：

```bash
C:\Users\DHB_HOME\opense\Scripts\python.exe -m pip install PySide6 pywin32
```

## 架构

一个 PySide6 单窗口桌面应用，通过 win32com COM 自动化操控 AutoCAD，批量修改 DWG 文件中的块属性值。

| 文件 | 职责 |
|---|---|
| `main.py` | 入口，创建 QApplication + MainWindow |
| `ui_main.py` | `MainWindow` — 全部 UI 布局和回调逻辑 |
| `cad_engine.py` | `CADEngine` — AutoCAD COM 连接、选块、批量更新 |
| `batch_worker.py` | `BatchWorker(QThread)` — 后台线程，逐文件调用 CADEngine |

**数据流**: 用户在 AutoCAD 中选块 → 读取属性标签填充表格 → 用户勾选标签并输入新值 → 加载 DWG 文件列表 → 确认后 QThread 后台逐文件打开、匹配、更新、保存。

## 关键设计点

- **COM 线程模型**: 每个使用 COM 的线程必须独立调用 `pythoncom.CoInitialize()`/`CoUninitialize()`。`BatchWorker.run()` 创建自己的 `CADEngine` 实例，不与主线程共享。
- **块匹配逻辑**: 仅当 DWG 中某个块参照包含**用户勾选的全部属性标签**时才更新（`required_set.issubset(block_tags)`）。不按块名匹配。
- **直接覆盖**: `doc.Save()` 就地把原文件覆盖，无备份。UI 在开始处理前弹出不可撤销警告。
- **ProgID 回退链**: `cad_engine.py:19-25` 按 2026 → 2025 → 2024 → 2023 → 通用顺序尝试连接 AutoCAD。
