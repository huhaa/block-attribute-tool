# 块属性批量填写工具

通过 COM 自动化操控 AutoCAD，批量修改多个 DWG 文件中块参照的属性值。适用隧道衬砌、市政管廊等需要大量重复填写块属性的场景。

## 功能

- **点选读取** — 连接 AutoCAD，在图中点选一个带属性的块参照，自动读取所有属性标签、当前值和提示词
- **灵活编辑** — 表格展示属性字段，支持：
  - 勾选需要处理的字段（未勾选的字段不会被匹配或修改）
  - 输入新属性值（每个字段独立编辑）
  - Shift/Ctrl 多选行 + 批量勾选联动
- **文件管理** — 支持添加、删除选中、清空 DWG 文件列表，实时显示文件数量
- **批量处理** — 后台线程逐文件处理，不阻塞 UI：
  - 支持选择处理范围：模型空间（ModelSpace）和/或布局空间（Layouts）
  - 实时日志输出 + 进度指示
  - 可中途取消处理
- **匹配逻辑** — 仅更新**包含全部勾选属性标签**的块参照（不按块名匹配）

## 环境要求

- Windows 10/11
- AutoCAD 2016 及以上版本（COM 接口兼容）
- Python 3.12+

## 安装

```bash
# 克隆仓库
git clone https://github.com/huhaa/block-attribute-tool.git
cd block-attribute-tool

# 创建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\activate
pip install PySide6 pywin32
```

## 使用

```bash
python main.py
```

1. 在 AutoCAD 中打开一个含属性块的 DWG
2. 点击 **🎯 选择块** → 在 CAD 中点选块 → 属性自动填入表格
3. 勾选要处理的字段，在"新值"列输入目标值
4. 点击 **📂 载入 DWG** 添加待处理文件
5. 勾选处理范围（模型空间 / 布局空间）
6. 点击 **🚀 开始处理** → 确认覆盖警告 → 批量执行

## 文件结构

| 文件 | 职责 |
|------|------|
| `main.py` | 入口，创建 QApplication + MainWindow |
| `ui_main.py` | MainWindow — 全部 UI 布局和回调逻辑 |
| `cad_engine.py` | CADEngine — AutoCAD COM 连接、选块、批量更新（含 ROT 查找、多版本 ProgID 回退） |
| `batch_worker.py` | BatchWorker(QThread) — 后台线程，逐文件调用 CADEngine 并报告进度 |

## 注意事项

- 处理直接覆盖原 DWG 文件，无备份，请事先备份重要数据
- 首次使用建议用少量测试文件验证
- 块匹配基于属性标签集合，与块名称无关
- 处理期间 AutoCAD 界面可能短暂卡顿（COM 调用占用）
