"""
AutoCAD COM 交互模块

封装通过 win32com 与 AutoCAD 2026 通信的操作：
- 连接/断开 AutoCAD
- 让用户点选块、读取属性
- 打开 DWG 查找匹配块并更新属性
"""
import os
import time
from typing import Optional, List, Dict, Tuple

import pythoncom
import win32com.client

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
# 不同 AutoCAD 版本的 ProgID 候选，优先匹配已安装的最新版
_PROG_IDS = [
    "AutoCAD.Application.26.1",  # 2026
    "AutoCAD.Application.26",    # 2025
    "AutoCAD.Application.25.1",  # 2024
    "AutoCAD.Application.25",    # 2023
    "AutoCAD.Application.24.1",  # 2022
    "AutoCAD.Application.24",    # 2021
    "AutoCAD.Application.23.1",  # 2020
    "AutoCAD.Application.23",    # 2019
    "AutoCAD.Application.22",    # 2018
    "AutoCAD.Application.21",    # 2017
    "AutoCAD.Application.20.1",  # 2016
    "AutoCAD.Application.20",    # 2015
    "AutoCAD.Application",       # 通用兜底
]


def _find_running_autocad():
    """遍历 ROT 查找任意正在运行的 AutoCAD 实例（ProgID 无关）。"""
    import pythoncom
    try:
        rot = pythoncom.GetRunningObjectTable()
        enum = rot.EnumRunning()
        bind_ctx = pythoncom.CreateBindCtx()
        while True:
            try:
                monikers = enum.Next(1)
                if not monikers:
                    break
                display = monikers[0].GetDisplayName(bind_ctx, None)
                if "autocad" in display.lower():
                    return rot.GetObject(monikers[0])
            except Exception:
                continue  # 跳过本次失败，继续检查下一条
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# CADEngine
# ---------------------------------------------------------------------------
class CADEngine:
    """AutoCAD COM 操作封装。

    用法:
        engine = CADEngine()
        if engine.connect():
            info = engine.pick_block()        # 用户点选块
            result = engine.update_blocks_in_dwg(path, tags, values)
        engine.close()
    """

    def __init__(self):
        self.acad = None          # Application 对象
        self.doc = None           # ActiveDocument
        self._owns_com = False    # 是否由本实例初始化了 COM

    # ----- 连接 / 断开 ------------------------------------------------

    def connect(self) -> bool:
        """连接到正在运行的 AutoCAD，或启动新实例。

        优先连接已运行的实例（任意版本），避免启动错误版本。
        """
        self._owns_com = True
        pythoncom.CoInitialize() # 初始化 COM

        # 第一步：在所有 ProgID 中搜索已运行的实例
        for prog_id in _PROG_IDS:
            try:
                self.acad = win32com.client.GetActiveObject(prog_id)
                break
            except Exception:
                continue

        # 第二步：若 ProgID 匹配不到，遍历 ROT 直接查找任意 AutoCAD
        if self.acad is None:
            self.acad = _find_running_autocad()

        # 第三步：没找到运行中的实例，才启动新的
        if self.acad is None:
            for prog_id in _PROG_IDS:
                try:
                    self.acad = win32com.client.Dispatch(prog_id)
                    break
                except Exception:
                    continue

        if self.acad is None:
            return False

        try:
            self.doc = self.acad.ActiveDocument
        except Exception:
            self.doc = None

        if self.doc is None:
            self.close()
            return False

        return True

    def close(self):
        """释放 COM 引用，不关闭 AutoCAD。"""
        try:
            pythoncom.CoUninitialize() # 释放 COM 引用
        except Exception:
            pass
        self.acad = None
        self.doc = None

    # ----- 用户点选块 ------------------------------------------------

    def pick_block(self) -> Dict[str, str | dict]:
        """让用户在 CAD 图中点选一个**带属性**的块参照。

        Returns:
            成功: {"属性标签1": "当前值1", "属性标签2": "当前值2", ...}
            失败: {"_error": "错误描述"}
        """
        if self.acad is None:
            return {"_error": "未连接到 AutoCAD，请先调用 connect()"}

        if self.doc is None:
            return {"_error": "AutoCAD 中没有打开的文档，请先打开一个 DWG 文件"}

        # 确保 AutoCAD 可见，让用户可以点选
        self.acad.Visible = True

        utility = self.doc.Utility
        prompt = "请点选一个带属性的块，然后按回车..."

        try:
            # 晚期绑定下 [out] 参数需传 None 占位，pywin32 在返回值元组中返回它们
            raw = utility.GetEntity(None, None, prompt) #(entity_object,pick_point,return_value)
            entity = raw[0] if isinstance(raw, tuple) else raw

            if entity is None:
                return {"_error": "未选中任何对象"}

            obj_name = entity.ObjectName
            if obj_name != "AcDbBlockReference":
                return {"_error": f"选中的不是块参照，而是: {obj_name}"}

            # 尝试获取属性
            try:
                attrs = entity.GetAttributes()
            except Exception:
                attrs = None

            if attrs is None or (hasattr(attrs, "__len__") and len(attrs) == 0):
                return {"_error": "选中的块没有属性定义 (ATTDEF)"}

            # 从块定义中读取 PromptString（属性参照上拿不到这个字段）
            prompt_map: Dict[str, str] = {}
            try:
                blk_name = str(entity.EffectiveName)
                blk_def = self.doc.Blocks.Item(blk_name)
                for item in blk_def:
                    if item.ObjectName == "AcDbAttributeDefinition":
                        prompt_map[str(item.TagString)] = str(item.PromptString)
            except Exception:
                pass

            result: Dict[str, dict] = {}
            for attr in attrs:
                tag = str(attr.TagString)
                result[tag] = {
                    "value": str(attr.TextString),
                    "prompt": prompt_map.get(tag, ""),
                }

            # 同时记录块名（仅用于显示，不用于匹配）
            try:
                result["__block_name__"] = str(entity.Name)
            except Exception:
                result["__block_name__"] = ""

            return result

        except Exception as e:
            return {"_error": f"选择出错: {str(e)}"}

    # ----- 内部辅助 --------------------------------------------------

    def _find_open_document(self, abs_path: str):
        """在已打开文档中查找匹配路径的文档，未找到返回 None。"""
        try:
            for doc in self.acad.Documents:
                try:
                    if os.path.normcase(doc.FullName) == os.path.normcase(abs_path):
                        return doc
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ----- 内部：遍历空间实体 ------------------------------------------

    def _collect_from_space(
        self,
        block,
        required_set: set,
        values: Dict[str, str],
    ) -> Tuple[int, int]:
        """遍历一个空间（模型/布局）中匹配的块参照并更新属性。

        Args:
            block: 可遍历的 Block 对象（ModelSpace 或 Layout.Block）
            required_set: 必须匹配的属性标签集合
            values: {tag: new_value} 映射

        Returns:
            (updated, skipped)
        """
        updated = 0
        skipped = 0
        count = block.Count

        for i in range(count):
            try:
                entity = block.Item(i)
                if entity.ObjectName != "AcDbBlockReference":
                    continue
            except Exception:
                continue  # 跳过无效实体（已擦除/代理对象/自定义对象等）

            try:
                attrs = entity.GetAttributes()
            except Exception:
                continue

            if attrs is None or (hasattr(attrs, "__len__") and len(attrs) == 0):
                skipped += 1
                continue

            block_tags: set = set()
            attr_map: Dict[str, object] = {}
            for attr in attrs:
                tag = str(attr.TagString)
                block_tags.add(tag)
                attr_map[tag] = attr

            if required_set.issubset(block_tags):
                for tag, new_value in values.items():
                    if tag in attr_map:
                        try:
                            attr_map[tag].TextString = new_value
                        except Exception:
                            pass  # 常量属性不可写
                updated += 1
            else:
                skipped += 1

        return updated, skipped

    # ----- 批量更新（单个 DWG） ---------------------------------------

    def update_blocks_in_dwg(
        self,
        dwg_path: str,
        required_tags: List[str],
        values: Dict[str, str],
        include_model: bool = True,
        include_layouts: bool = False,
    ) -> Dict:
        """在单个 DWG 中查找属性标签覆盖 required_tags 的所有块并更新。

        内置重试：RPC_E_CALL_REJECTED 等 COM 忙错误会退避重试最多 10 次。
        """
        if self.acad is None:
            return {"updated": 0, "skipped": 0, "file": dwg_path,
                    "error": "未连接到 AutoCAD"}

        abs_path = os.path.abspath(dwg_path)
        if not os.path.isfile(abs_path):
            return {"updated": 0, "skipped": 0, "file": dwg_path,
                    "error": "文件不存在"}

        required_set = set(required_tags)
        last_error = None

        for attempt in range(10):
            doc = None
            should_close = False
            step = "init"
            try:
                doc = self._find_open_document(abs_path)
                if doc is None:
                    step = "Documents.Open"
                    doc = self.acad.Documents.Open(abs_path)
                    should_close = True
                    time.sleep(0.6)  # 等文档内部初始化完成

                updated = 0
                skipped = 0

                # -- 模型空间 --------------------------------------------
                if include_model:
                    step = "ModelSpace"
                    u, s = self._collect_from_space(
                        doc.ModelSpace, required_set, values
                    )
                    updated += u
                    skipped += s

                # -- 布局空间 --------------------------------------------
                if include_layouts:
                    step = "Layouts"
                    try:
                        layouts = doc.Layouts
                        for layout in layouts:
                            try:
                                layout_name = str(layout.Name)
                            except Exception:
                                continue
                            # 跳过模型布局（已单独处理）
                            if layout_name.lower() == "model":
                                continue
                            step = f"Layout[{layout_name}]"
                            try:
                                layout_block = layout.Block
                            except Exception:
                                continue
                            u, s = self._collect_from_space(
                                layout_block, required_set, values
                            )
                            updated += u
                            skipped += s
                    except Exception as e:
                        last_error = e
                        # 布局遍历失败不会阻止整体任务，记录到 skipped
                        skipped += 1

                step = "Save"
                doc.Save()
                if should_close:
                    step = "Close"
                    doc.Close()

                return {"updated": updated, "skipped": skipped,
                        "file": dwg_path, "error": None}

            except Exception as e:
                last_error = e
                if should_close and doc is not None:
                    try:
                        doc.Close()
                    except Exception:
                        pass

                err_str = str(e)
                if ("被呼叫方拒绝" in err_str
                        or "RPC_E_CALL_REJECTED" in err_str
                        or "ModelSpace" in err_str
                        or "Layout" in err_str):
                    time.sleep(1.0 + attempt * 0.8)
                    continue
                # 其他错误直接返回，不重试
                break

        return {"updated": 0, "skipped": 0, "file": dwg_path,
                "error": f"[{step}] {last_error}"}
