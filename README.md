# 块属性批量填写工具

通过 COM 自动化操控 AutoCAD，批量修改多个 DWG 文件中块参照的属性值。

## 功能

- 从 AutoCAD 图中点选块，自动读取属性标签、当前值和提示词
- 表格勾选需要处理的属性字段，填写新值
- 加载多个 DWG 文件，批量查找匹配的块并更新属性
- 匹配逻辑：仅更新**包含全部勾选属性标签**的块参照（不按块名）
- 支持 Shift/Ctrl 多选、批量勾选联动、选中文件删除

## 环境要求

- Windows 10/11
- AutoCAD 2023–2026
- [Python 3.12+](https://www.python.org/)

## 安装

```bash
# 克隆仓库
git clone https://github.com/你的用户名/block-attribute-tool.git
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
2. 点击 **选择块** → 在 CAD 中点选块 → 属性自动填入表格
3. 勾选要处理的字段，填入新属性值
4. 点击 **载入 DWG** 添加待处理文件
5. 点击 **开始处理** → 确认覆盖警告 → 批量执行

## 文件结构

| 文件 | 职责 |
|------|------|
| `main.py` | 入口，创建 QApplication + MainWindow |
| `ui_main.py` | MainWindow — 全部 UI 布局和回调逻辑 |
| `cad_engine.py` | CADEngine — AutoCAD COM 连接、选块、批量更新 |
| `batch_worker.py` | BatchWorker(QThread) — 后台线程，逐文件处理 |

## 注意事项

- 处理直接覆盖原文件，无备份，请事先备份重要数据
- 首次使用建议用少量测试文件验证
- 仅更新模型空间（ModelSpace）中的块参照
