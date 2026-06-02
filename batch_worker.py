"""
批量处理工作线程

在 QThread 后台依次打开每个 DWG，调用 CADEngine.update_blocks_in_dwg，
并通过 Signal 向主界面报告进度和结果。
"""
import time
from typing import List, Dict

from PySide6.QtCore import QThread, Signal

from cad_engine import CADEngine


class BatchWorker(QThread):
    """后台批量处理工作线程。"""

    # ---- 信号 --------------------------------------------------------
    progress = Signal(str)       # 状态消息（文件级）
    file_done = Signal(dict)     # 单个文件的结果字典
    all_done = Signal()          # 全部处理完成

    def __init__(
        self,
        dwg_files: List[str],
        required_tags: List[str],
        values: Dict[str, str],
        include_model: bool = True,
        include_layouts: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.dwg_files = dwg_files
        self.required_tags = required_tags
        self.values = values
        self.include_model = include_model
        self.include_layouts = include_layouts
        self._cancelled = False

    # ----- 公共方法 ---------------------------------------------------

    def cancel(self):
        """请求取消处理（当前文件处理完后退出循环）。"""
        self._cancelled = True

    # ----- 线程主体 ---------------------------------------------------

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()

        engine = CADEngine()
        if not engine.connect():
            self.progress.emit("❌ 无法连接到 AutoCAD，请确认已安装并至少启动过一次。")
            pythoncom.CoUninitialize()
            self.all_done.emit()
            return

        total = len(self.dwg_files)
        self.progress.emit(f"📦 开始处理 {total} 个文件...")

        succeeded = 0
        failed = 0

        for idx, dwg_path in enumerate(self.dwg_files, start=1):
            if self._cancelled:
                self.progress.emit("⏹ 处理已取消")
                break

            self.progress.emit(f"[{idx}/{total}] 📄 {dwg_path}")

            result = engine.update_blocks_in_dwg(
                dwg_path,
                self.required_tags,
                self.values,
                include_model=self.include_model,
                include_layouts=self.include_layouts,
            )

            self.file_done.emit(result)

            if result.get("error"):
                failed += 1
            else:
                succeeded += 1

            # 给 AutoCAD 留出内部清理时间，防止下一个 Open 被拒绝
            time.sleep(0.3)

        # 汇总
        self.progress.emit(
            f"✅ 处理完成！成功 {succeeded} 个，失败 {failed} 个，"
            f"共 {total} 个文件。"
        )

        engine.close()
        pythoncom.CoUninitialize()
        self.all_done.emit()
