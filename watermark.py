# -*- coding: utf-8 -*-
"""watermark.py — 「图片加密」的隐写水印配置面板（v2.0.1 重构）。

与 v2.0.0 的差别：
- 只负责右栏配置与处理逻辑，文件列表/预览由主窗口共用面板提供
- 「输出文件夹 / 浏览 / 存为默认」整行移除——输出由全局设置统一管理，
  嵌入结果直接保存到 根目录\\隐写水印
- 「移除选中」改名为「移除」（按钮行由主窗口统一提供）
功能逻辑不变：文字/图片水印嵌入、批量、容量校验、防覆盖命名、
提取参数按文件名自动识别、图片水印宽x高、后台线程与日志。
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402
import mixer  # noqa: E402  （检测源文件名是否含混淆元信息段，用于双段叠加命名）
from PySide6.QtCore import Qt, QThread, Signal  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QWidget, QLabel, QPushButton, QButtonGroup, QLineEdit, QTextEdit,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
)


def _init_engine():
    """初始化水印引擎（cv2 + wm_core）。

    必须在 QApplication 创建之后调用，这样失败时才能正常弹窗提示用户。
    直接使用真实 OpenCV（opencv-python-headless）——伪造的 cv2 stub 会让
    DCT/SVD 全部失真，是历史上「点击嵌入就崩溃」的根本原因。
    """
    global cv2, WaterMark
    import cv2 as _cv2
    cv2 = _cv2
    from wm_core import WaterMark as _WM
    WaterMark = _WM


class WorkerThread(QThread):
    """后台线程，用于执行耗时的水印操作，防止 UI 卡顿。

    不能自定义名为 ``finished`` 的信号（会遮蔽 QThread 内置信号），
    改用 ``result`` 信号回传结果。
    """

    result = Signal(str)
    error = Signal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            value = self._func(*self._args, **self._kwargs)
            self.result.emit(str(value))
        except Exception as exc:
            tb = traceback.format_exc()
            self.error.emit(f"{exc}\n{tb}")


class WatermarkConfig(QWidget):
    """隐写水印配置面板：嵌入/提取段选切换 + 密码共用 + 日志。"""

    status_msg = Signal(str)   # 状态消息 → 主窗口底栏
    busy_sig = Signal(bool)    # 忙碌状态 → 主窗口顶栏状态点

    def __init__(self, main):
        super().__init__()
        self._main = main
        self._active_threads = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        rv = QVBoxLayout(self)
        rv.setContentsMargins(6, 14, 14, 14)
        rv.setSpacing(6)

        # 模式段选：嵌入 / 提取
        rv.addWidget(self._section('模式'))
        mseg = QWidget()
        ml = QHBoxLayout(mseg)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(8)
        self.mode_embed = self._seg('嵌入水印', '把文字/图片水印嵌入原图（可批量）')
        self.mode_extract = self._seg('提取水印', '从嵌入后的图片中提取水印（可批量）')
        self.mode_grp = QButtonGroup(self)
        self.mode_grp.setExclusive(True)
        for b in (self.mode_embed, self.mode_extract):
            self.mode_grp.addButton(b)
            b.toggled.connect(self._on_mode_changed)
            ml.addWidget(b, 1)
        self.mode_embed.setChecked(True)
        rv.addWidget(mseg)
        rv.addSpacing(10)

        # 密码（嵌入/提取共用：嵌入后切提取无需重填；窄栏竖排两行）
        prow = QHBoxLayout()
        prow.setSpacing(10)
        prow.addWidget(QLabel('密码img'))
        self.pwd_img = QLineEdit()
        self.pwd_img.setPlaceholderText('自然数')
        prow.addWidget(self.pwd_img, 1)
        rv.addLayout(prow)
        prow2 = QHBoxLayout()
        prow2.setSpacing(10)
        prow2.addWidget(QLabel('密码wm'))
        self.pwd_wm = QLineEdit()
        self.pwd_wm.setPlaceholderText('自然数')
        prow2.addWidget(self.pwd_wm, 1)
        rv.addLayout(prow2)
        rv.addSpacing(10)

        # ---- 嵌入配置组 ----
        self.embed_group = QWidget()
        ev = QVBoxLayout(self.embed_group)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(6)

        # 水印类型段选
        ev.addWidget(self._section('水印类型'))
        tseg = QWidget()
        tl = QHBoxLayout(tseg)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        self.wm_text = self._seg('文字', '把文字内容嵌入图片')
        self.wm_img = self._seg('图片', '把一张图片作为水印嵌入')
        self.wm_grp = QButtonGroup(self)
        self.wm_grp.setExclusive(True)
        for b in (self.wm_text, self.wm_img):
            self.wm_grp.addButton(b)
            b.toggled.connect(self._on_wm_type_changed)
            tl.addWidget(b, 1)
        self.wm_text.setChecked(True)
        ev.addWidget(tseg)

        # 文字内容（文字模式显示）
        self.text_row = QWidget()
        tr_ = QVBoxLayout(self.text_row)
        tr_.setContentsMargins(0, 0, 0, 0)
        tr_.setSpacing(4)
        self.embed_text = QTextEdit()
        self.embed_text.setPlaceholderText('请输入文本')
        self.embed_text.setFixedHeight(72)
        tr_.addWidget(self.embed_text)
        ev.addWidget(self.text_row)

        # 水印图片（图片模式显示）+ 48px 微预览
        self.img_row = QWidget()
        ir = QVBoxLayout(self.img_row)
        ir.setContentsMargins(0, 0, 0, 0)
        ir.setSpacing(4)
        wrow = QHBoxLayout()
        wrow.setSpacing(8)
        self.embed_wm_file = QLineEdit()
        self.embed_wm_preview = QLabel()
        self.embed_wm_preview.setFixedSize(48, 48)
        self.embed_wm_file.textChanged.connect(self._update_wm_preview)
        b_browse_wm = QPushButton('浏览')
        b_browse_wm.setObjectName('minorBtn')
        b_browse_wm.clicked.connect(self._browse_wm_file)
        wrow.addWidget(self.embed_wm_file, 1)
        wrow.addWidget(b_browse_wm)
        wrow.addWidget(self.embed_wm_preview)
        ir.addLayout(wrow)
        ev.addWidget(self.img_row)
        ev.addSpacing(8)

        self.embed_btn = QPushButton('开始嵌入')
        self.embed_btn.setObjectName('encBtn')
        self.embed_btn.clicked.connect(self._run_embed)
        ev.addWidget(self.embed_btn)
        rv.addWidget(self.embed_group)

        # ---- 提取配置组 ----
        self.extract_group = QWidget()
        xv = QVBoxLayout(self.extract_group)
        xv.setContentsMargins(0, 0, 0, 0)
        xv.setSpacing(6)

        xv.addWidget(self._section('提取模式'))
        eseg = QWidget()
        el = QHBoxLayout(eseg)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(8)
        self.ex_str = self._seg('文字', '提取文字水印（字符串）')
        self.ex_bit = self._seg('位图', '提取位图水印（0/1 数组）')
        self.ex_img = self._seg('图片', '提取图片水印（保存到源文件旁）')
        self.ex_grp = QButtonGroup(self)
        self.ex_grp.setExclusive(True)
        for b in (self.ex_str, self.ex_bit, self.ex_img):
            self.ex_grp.addButton(b)
            el.addWidget(b, 1)
        self.ex_str.setChecked(True)
        xv.addWidget(eseg)
        xv.addSpacing(8)

        bits_row = QHBoxLayout()
        bits_row.setSpacing(10)
        bits_row.addWidget(QLabel('水印位数'))
        self.extract_bits = QLineEdit()
        self.extract_bits.setPlaceholderText('留空自动；图片水印可填 宽x高 如 20x20')
        bits_row.addWidget(self.extract_bits, 1)
        xv.addLayout(bits_row)
        hint = QLabel('密码与位数留空时，按文件名「序号-img-wm-bits」自动识别')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #8a7f75; font-size: 11px;')
        xv.addWidget(hint)
        xv.addSpacing(8)

        self.extract_btn = QPushButton('开始提取')
        self.extract_btn.setObjectName('decBtn')
        self.extract_btn.clicked.connect(self._run_extract)
        xv.addWidget(self.extract_btn)
        rv.addWidget(self.extract_group)

        # 日志（两模式共用）
        rv.addSpacing(10)
        rv.addWidget(self._section('日志'))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        rv.addWidget(self.log, 1)

        self._on_mode_changed()
        self._on_wm_type_changed()

    # ------------------------------------------------------------------
    # UI 小件
    # ------------------------------------------------------------------
    @staticmethod
    def _section(text: str) -> QLabel:
        """小节标题：小字、字距、弱化色。"""
        lab = QLabel(text)
        lab.setStyleSheet(
            'color: #8a7f75; font-size: 11px; letter-spacing: 2px; font-weight: 600;')
        return lab

    @staticmethod
    def _seg(text: str, tip: str) -> QPushButton:
        """分段选择按钮：并排单选，选中番茄红描边。"""
        b = QPushButton(text)
        b.setObjectName('segBtn')
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        return b

    def _status(self, text: str):
        self.status_msg.emit(text)

    def _on_mode_changed(self):
        if not hasattr(self, 'embed_group'):
            return  # 构造期默认选中即触发，此时控件尚未建全
        embed = self.mode_embed.isChecked()
        self.embed_group.setVisible(embed)
        self.extract_group.setVisible(not embed)

    def _on_wm_type_changed(self):
        if not hasattr(self, 'text_row'):
            return
        is_img = self.wm_img.isChecked()
        self.text_row.setVisible(not is_img)
        self.img_row.setVisible(is_img)

    def _browse_wm_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择水印图片', '',
            '图片 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)')
        if file_path:
            self.embed_wm_file.setText(file_path)

    def _update_wm_preview(self):
        """水印图片行的 48px 微型预览；路径为空/读不出则清空。"""
        pix = QPixmap(self.embed_wm_file.text().strip())
        if not pix.isNull():
            self.embed_wm_preview.setPixmap(
                pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.embed_wm_preview.clear()

    # ------------------------------------------------------------------
    # 引擎辅助
    # ------------------------------------------------------------------
    def _read_image_or_none(self, path):
        """读取图片（np.fromfile + imdecode 兼容中文路径）；失败弹窗并返回 None。"""
        try:
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                QMessageBox.warning(self, "文件错误",
                                    f"无法读取图片：\n{path}\n\n请确认文件路径正确且文件未损坏。")
            return img
        except Exception as e:
            QMessageBox.warning(self, "文件错误", f"无法读取图片：\n{path}\n\n{e}")
            return None

    @staticmethod
    def _capacity(img):
        """返回图片可容纳的水印位数（与 blind_watermark 分块逻辑一致）。"""
        h, w = img.shape[:2]
        return ((h + 1) // 2 // 4) * ((w + 1) // 2 // 4)

    def _start_worker(self, func, *args):
        """启动后台线程执行水印操作（内置 finished 信号做安全清理）。"""
        thread = WorkerThread(func, *args)
        self._active_threads.append(thread)
        self.busy_sig.emit(True)
        self._status('处理中…')
        thread.result.connect(lambda msg: self.log.append(msg))
        thread.error.connect(lambda e: self.log.append(f"错误: {e}"))
        thread.finished.connect(lambda t=thread: self._on_thread_done(t))
        thread.start()

    def _on_thread_done(self, thread):
        """线程真正停止后的安全清理。"""
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        if not self._active_threads:
            self.busy_sig.emit(False)
            self._status('完成')
        thread.deleteLater()

    def _next_output_name(self, out_dir, pwd_img, pwd_wm, bits, ext, src_stem=''):
        """生成不覆盖已有文件的输出名。
        源文件名带混淆元信息段 → 双段叠加：源段原样在前（序号保持第一位），
        新水印段去序号只留 img-wm-bits，如 001-GC-密钥_7-9-96.png。
        普通图 → 现状模板：序号-img-wm-bits。"""
        out_dir = Path(out_dir)
        ext = ext if ext.startswith(".") else "." + ext
        if src_stem:
            stem = f"{src_stem}_{pwd_img}-{pwd_wm}-{bits}"
            if not (out_dir / (stem + ext)).exists():
                return out_dir / (stem + ext)
            for i in range(1, 1000):
                q = out_dir / f"{stem} ({i}){ext}"
                if not q.exists():
                    return q
            return out_dir / (stem + ext)
        seq = 1
        while True:
            name = f"{seq}-{pwd_img}-{pwd_wm}-{bits}{ext}"
            if not (out_dir / name).exists():
                return out_dir / name
            seq += 1

    # ------------------------------------------------------------------
    # 嵌入水印（输出直接进 根目录\隐写水印，由全局设置统一管理）
    # ------------------------------------------------------------------
    def _run_embed(self):
        files = self._main.file_paths()
        out_dir = self._main.subdir('隐写水印')
        if not files:
            QMessageBox.warning(self, "缺少参数", "请选择原图文件。")
            return
        try:
            pwd_img = int(self.pwd_img.text().strip())
            pwd_wm = int(self.pwd_wm.text().strip())
        except ValueError:
            QMessageBox.warning(self, "参数错误", "密码必须为整数。")
            return

        if self.wm_img.isChecked():
            # 图片水印模式
            wm_path = self.embed_wm_file.text().strip()
            if not wm_path:
                QMessageBox.warning(self, "缺少参数", "请选择水印图片。")
                return
            wm_img = self._read_image_or_none(wm_path)
            if wm_img is None:
                return
            wm_bits = wm_img.shape[0] * wm_img.shape[1]  # 图片水印位数=像素总数
            for src in files:
                src_img = self._read_image_or_none(src)
                if src_img is None:
                    return
                if wm_bits > self._capacity(src_img):
                    QMessageBox.warning(
                        self, "水印太大",
                        f"文件 {src} 水印位数 {wm_bits} 超过可嵌入容量 "
                        f"{self._capacity(src_img)}，请使用更小的水印或更大的原图。")
                    return
            wm_arg, mode = wm_path, "img"
        else:
            # 文字水印模式
            text = self.embed_text.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "缺少参数", "请输入文字水印内容。")
                return
            text_bits = len(text.encode("utf-8")) * 8
            for src in files:
                src_img = self._read_image_or_none(src)
                if src_img is None:
                    return
                if text_bits > self._capacity(src_img):
                    QMessageBox.warning(
                        self, "文字水印太大",
                        f"文件 {src} 文字位数 {text_bits} 超过可嵌入容量 "
                        f"{self._capacity(src_img)}，请使用更短的文字或更大的原图。")
                    return
            wm_arg, mode = text, "str"

        self.log.append("开始嵌入…")
        self._start_worker(self._embed_worker, files, mode, wm_arg, str(out_dir), pwd_img, pwd_wm)

    def _embed_worker(self, files, mode, wm_arg, out_dir, pwd_img, pwd_wm):
        """对每个原图嵌入同一水印（1 个=单文件，多个=批量；单张失败不中断）。"""
        outer = Path(out_dir)
        outer.mkdir(parents=True, exist_ok=True)
        total = len(files)
        lines = []
        for i, src in enumerate(files, 1):
            try:
                bwm = WaterMark(password_wm=pwd_wm, password_img=pwd_img)
                bwm.read_img(src)
                if mode == "img":
                    bwm.read_wm(wm_arg)
                    bits = len(bwm.wm_bit)
                else:
                    bwm.read_wm(wm_arg, mode="str")
                    bits = len(wm_arg.encode("utf-8")) * 8
                ext = Path(src).suffix
                # 源文件名含混淆元信息段时保留（双段叠加：混淆段_水印段）
                src_stem = Path(src).stem if mixer.MixerConfig._parse_name(src) is not None else ''
                out_path = self._next_output_name(out_dir, pwd_img, pwd_wm, bits, ext, src_stem)
                bwm.embed(str(out_path))
                lines.append(f"[{i}/{total}] 已生成 {out_path}")
            except Exception as e:
                lines.append(f"[{i}/{total}] 跳过 {src}: {e}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 提取水印
    # ------------------------------------------------------------------
    @staticmethod
    def _opt_int(text):
        """空串→None（自动模式）；非空但非整数→ValueError。"""
        text = text.strip()
        return int(text) if text else None

    @staticmethod
    def _parse_bits(text):
        """『水印位数』：空→None；纯数字→int；宽x高（如 20x20）→(宽, 高)。"""
        t = text.strip().lower().replace("*", "x")
        if not t:
            return None
        if "x" in t:
            w, h = [int(p) for p in t.split("x")]
            return (w, h)
        return int(t)

    @staticmethod
    def _parse_wm_name(stem):
        """解析水印段。两种形态（段间 '_' 连接，分段扫描第一个可识别段）：
        - 带序号：序号-img-wm-bits（单模式输出/旧格式，如 1-7-9-96）
        - 去序号：img-wm-bits（双段叠加里的新段，如 001-GC-密钥_7-9-96 的 7-9-96）
        混淆段第二位恒为 GC/RO/BS 字母，不会被全数字段判定误认。"""
        for part in stem.split('_'):
            segs = part.split('-')
            if len(segs) == 4 and all(s.isdigit() for s in segs):
                return int(segs[1]), int(segs[2]), int(segs[3])
            if len(segs) == 3 and all(s.isdigit() for s in segs):
                return int(segs[0]), int(segs[1]), int(segs[2])
        return None

    def _run_extract(self):
        files = self._main.file_paths()
        try:
            pwd_img = self._opt_int(self.pwd_img.text())
            pwd_wm = self._opt_int(self.pwd_wm.text())
            bits = self._parse_bits(self.extract_bits.text())
        except ValueError:
            QMessageBox.warning(
                self, "参数错误",
                "密码必须为整数；水印位数须为数字或「宽x高」（如 20x20）。")
            return
        mode = 'str' if self.ex_str.isChecked() else (
            'bit' if self.ex_bit.isChecked() else 'img')
        if not files:
            QMessageBox.warning(self, "缺少参数", "请选择嵌入后图片文件。")
            return
        if pwd_img is None or pwd_wm is None or bits is None:
            self.log.append("参数留空：按文件名「序号-img-wm-bits」自动识别…")
        self.log.append("开始提取水印…")
        self._start_worker(self._extract_worker, files, pwd_img, pwd_wm, bits, mode)

    def _extract_worker(self, files, pwd_img, pwd_wm, bits, mode):
        """批量提取；留空参数从文件名自动识别，识别失败逐条提示，不中断。"""
        total = len(files)
        lines = []
        for i, src in enumerate(files, 1):
            try:
                # 用户手填的优先；留空的用文件名「序号-img-wm-bits」自动识别
                auto = self._parse_wm_name(Path(src).stem)
                p_img = pwd_img if pwd_img is not None else (auto[0] if auto else None)
                p_wm = pwd_wm if pwd_wm is not None else (auto[1] if auto else None)
                b_bits = bits if bits is not None else (auto[2] if auto else None)
                if p_img is None or p_wm is None:
                    lines.append(f"[{i}/{total}] {src}\n自动提取失败，请手动输入。")
                    continue
                bwm = WaterMark(password_wm=p_wm, password_img=p_img)
                if mode == "img":
                    # 图片水印提取：位数框可填 宽x高（如 20x20）；只有总位数时按方形重建
                    if isinstance(b_bits, tuple):
                        shape = b_bits
                    elif isinstance(b_bits, int):
                        r = round(b_bits ** 0.5)
                        if r * r != b_bits:
                            lines.append(f"[{i}/{total}] {src}\n自动提取失败，请手动输入。")
                            continue
                        shape = (r, r)
                        lines.append(f"[{i}/{total}] {src}\n提示：水印位数 {b_bits}，按方形 {r}x{r} 重建")
                    else:
                        lines.append(f"[{i}/{total}] {src}\n自动提取失败，请手动输入。")
                        continue
                    out_path = Path(src).with_name(Path(src).stem + "_extracted.png")
                    bwm.extract(filename=src, wm_shape=shape, out_wm_name=str(out_path))
                    lines.append(f"[{i}/{total}] {src}\n提取到图片水印, 已保存至 {out_path}")
                else:
                    n = b_bits[0] * b_bits[1] if isinstance(b_bits, tuple) else b_bits
                    if n is None:
                        lines.append(f"[{i}/{total}] {src}\n自动提取失败，请手动输入。")
                        continue
                    result = bwm.extract(filename=src, wm_shape=n, mode=mode)
                    kind = "文字" if mode == "str" else "位图"
                    lines.append(f"[{i}/{total}] {src}\n提取到{kind}水印: {result}")
            except Exception as e:
                lines.append(f"[{i}/{total}] {src}\n提取失败: {e}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 退出时清理线程
    # ------------------------------------------------------------------
    def stop_threads(self):
        """主窗口关闭时调用：安全退出仍在运行的线程。"""
        for thread in list(self._active_threads):
            try:
                thread.quit()
                thread.wait(3000)
            except Exception:
                pass
        self._active_threads.clear()
