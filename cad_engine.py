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
    "AutoCAD.Application.26.1",  # AutoCAD 2026
    "AutoCAD.Application.26",    # AutoCAD 2025
    "AutoCAD.Application.25.1",  # AutoCAD 2024
    "AutoCAD.Application.25",    # AutoCAD 2023
    "AutoCAD.Application",       # 通用（2016 及更早版本均支持）
]


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
        """连接到正在运行的 AutoCAD，或启动新实例。"""
        self._owns_com = True
        pythoncom.CoInitialize()

        # 尝试各种 ProgID
        for prog_id in _PROG_IDS:
            try:
                self.acad = win32com.client.GetActiveObject(prog_id)
                break
            except Exception:
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
            pythoncom.CoUninitialize()
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
            raw = utility.GetEntity(None, None, prompt)
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

    # ----- 批量更新（单个 DWG） ---------------------------------------

    def update_blocks_in_dwg(
        self,
        dwg_path: str,
        required_tags: List[str],
        values: Dict[str, str],
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

                step = "ModelSpace"
                model_space = doc.ModelSpace
                count = model_space.Count

                updated = 0
                skipped = 0

                for i in range(count):
                    step = f"entity[{i}]"
                    entity = model_space.Item(i)
                    if entity.ObjectName != "AcDbBlockReference":
                        continue

                    step = f"GetAttributes[{i}]"
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
                        step = f"set_TextString[{i}]"
                        for tag, new_value in values.items():
                            if tag in attr_map:
                                try:
                                    attr_map[tag].TextString = new_value
                                except Exception:
                                    pass  # 常量属性不可写
                        updated += 1
                    else:
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
                        or "ModelSpace" in err_str):
                    time.sleep(1.0 + attempt * 0.8)
                    continue
                # 其他错误直接返回，不重试
                break

        return {"updated": 0, "skipped": 0, "file": dwg_path,
                "error": f"[{step}] {last_error}"}
