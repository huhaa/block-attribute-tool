r"""
块属性批量填写工具 — 入口

在指定的 Python 虚拟环境中运行:
    C:\Users\DHB_HOME\opense\Scripts\python.exe main.py
"""
import sys
import os

# 确保脚本所在目录在 sys.path 中，支持从任意目录运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui_main import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DHB块属性批量填写工具")

    # 设置全局字体（Windows 下更清晰）
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
