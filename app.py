# -*- coding: utf-8 -*-
"""app.py — 「图片加密」主程序：乱序混淆 + 隐写水印 双模式合一。

统一架构（v2.0.1 重构）：
- 顶栏：品牌 + 模式段选「乱序混淆|隐写水印」+ ⚙设置 + 状态点
- 左栏（两模式共用）：大预览 + 文件缩略条 + [选择图片|移除|清空]，切模式文件保留
- 右栏：QStackedWidget 只切配置面板（右栏宽度天然统一）
- 底栏：状态 + 版本
- 设置：默认输出文件夹（自动创建「乱序混淆」「隐写水印」两个子目录）

运行：python app.py
打包：py -m PyInstaller --noconfirm --clean ImageEncryption.spec
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _resource_path(name: str) -> str:
    """返回打包/源码两种运行场景下都能找对资源的路径。"""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / name)


try:
    from PySide6.QtCore import Qt, QStandardPaths, QSettings, QSize
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, QPushButton, QButtonGroup,
        QStackedWidget, QSplitter, QDialog, QLineEdit, QVBoxLayout,
        QHBoxLayout, QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    )
except Exception:
    _tb = traceback.format_exc()
    try:
        Path("error.log").write_text(_tb, encoding="utf-8")
    except Exception:
        pass
    sys.stderr.write(_tb)
    raise

import mixer  # noqa: E402
import watermark  # noqa: E402

APP_VERSION = '2.0.9'   # 版本唯一源：底栏显示与安装包版本对齐
LANG_COLOR = '#e8564a'  # 番茄红（品牌/主操作）
OK_COLOR = '#7fb069'    # 叶绿（就绪状态点）
OUT_SUBDIRS = ('乱序混淆', '隐写水印')  # 默认输出根目录下的两个子目录
EMPTY_HINT = '<div style="font-size:64px;">🔐</div>'
IMAGE_FILTER = '图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)'

DARK_QSS = """
* {
    font-family: "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
}
QWidget { background-color: #141210; color: #e6ded6; }
QMainWindow, QDialog { background-color: #141210; }
QLabel { background: transparent; }

#topbar, #bottombar { background-color: #191512; }
#topbar { border-bottom: 1px solid #2b2520; }
#bottombar { border-top: 1px solid #2b2520; }

#previewCanvas {
    background-color: #0f0d0b;
    border: 1px solid #2b2520;
    border-radius: 12px;
}

QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #211c17; }

QPushButton {
    background-color: #221e19;
    color: #b3a89c;
    border: 1px solid #342e27;
    border-radius: 8px;
    padding: 8px 12px;
}
QPushButton:hover { background-color: #2a241e; color: #e6ded6; }
QPushButton:pressed { background-color: #1a1613; }
QPushButton:disabled { color: #5c534a; background-color: #1a1613; border-color: #262019; }
QPushButton#segBtn { padding: 9px 6px; font-weight: 500; }
QPushButton#segBtn:checked {
    background-color: #2c1a17;
    border-color: #e8564a;
    color: #ef8d80;
}
QPushButton#segBtn:checked:hover { background-color: #33201b; }
QPushButton#minorBtn { color: #8a7f75; padding: 10px 12px; font-size: 14px; }
QPushButton#importBtn {
    background-color: transparent;
    border: 1px dashed #4a4038;
    color: #a89d90;
    padding: 10px 12px; font-size: 14px;
}
QPushButton#importBtn:hover { border-color: #e8564a; color: #e6ded6; }
QPushButton#encBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #e8564a, stop:1 #c7403a);
    color: #ffffff;
    border: 1px solid #ef6b5e;
    border-radius: 9px;
    padding: 10px 12px;
    font-weight: 700;
    font-size: 14px;
}
QPushButton#encBtn:hover { background: #ee645a; }
QPushButton#encBtn:pressed { background: #b83a34; }
QPushButton#decBtn {
    background-color: #26211b;
    color: #d8cfc4;
    border: 1px solid #3d362e;
    border-radius: 9px;
    padding: 10px 12px;
    font-weight: 600;
    font-size: 14px;
}
QPushButton#decBtn:hover { background-color: #2d2720; border-color: #4a4038; }
QPushButton#decBtn:pressed { background-color: #1c1813; }
QPushButton#gearBtn {
    background: transparent; border: none; color: #b3a89c;
    font-size: 18px; padding: 2px 10px;
}
QPushButton#gearBtn:hover { color: #f2ece5; }
QPushButton#okBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #e8564a, stop:1 #c7403a);
    color: #ffffff; border: 1px solid #ef6b5e;
    border-radius: 8px; padding: 8px 18px; font-weight: 600;
}
QPushButton#okBtn:hover { background: #ee645a; }
QPushButton#cancelBtn {
    background-color: #221e19; color: #b3a89c;
    border: 1px solid #342e27; border-radius: 8px; padding: 8px 18px;
}
QPushButton#cancelBtn:hover { background-color: #2a241e; color: #e6ded6; }

QLineEdit, QSpinBox, QTextEdit {
    background-color: #1c1814;
    border: 1px solid #342e27;
    border-radius: 8px;
    padding: 6px 10px;
    color: #f2ece5;
    selection-background-color: #e8564a;
}
QLineEdit:hover, QSpinBox:hover, QTextEdit:hover { border-color: #463e36; }
QLineEdit:focus, QSpinBox:focus, QTextEdit:focus { border: 1px solid #e8564a; }

QCheckBox { spacing: 10px; color: #cfc5b8; background: transparent; }
QCheckBox#xorCheck::indicator {
    width: 34px; height: 19px; border-radius: 10px;
    background-color: #262019; border: 1px solid #3d362e;
}
QCheckBox#xorCheck::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #e8564a, stop:1 #ef8d80);
    border: 1px solid #ef6b5e;
}
QCheckBox#xorCheck:hover::indicator { border-color: #e8564a; }

QProgressBar {
    background: #1c1814; border: 1px solid #342e27; border-radius: 6px;
    text-align: center; color: #a89d90; height: 18px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #e8564a, stop:1 #ef8d80);
    border-radius: 5px;
}

QListWidget {
    background-color: #0f0d0b; border: 1px solid #2b2520; border-radius: 10px;
}
QListWidget::item { color: #a89d90; padding: 4px; border-radius: 7px; }
QListWidget::item:selected {
    background-color: #2c1a17; color: #ef8d80; border: 1px solid #e8564a;
}
QListWidget::item:hover { background-color: #1c1814; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #342e27; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #463e36; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: #342e27; border-radius: 4px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #463e36; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


class FileListWidget(QListWidget):
    """缩略图条式文件列表（两模式共用）：拖入/多选，点击条目联动大预览。"""

    def __init__(self, win):
        super().__init__()
        self._win = win
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(64, 64))
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListWidget.Adjust)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFixedHeight(96)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths:
            self._win._add_files(paths)
            e.acceptProposedAction()


def _section(text: str) -> QLabel:
    """小节标题：小字、字距、弱化色。"""
    lab = QLabel(text)
    lab.setStyleSheet(
        'color: #8a7f75; font-size: 11px; letter-spacing: 2px; font-weight: 600;')
    return lab


class SettingsPage(QWidget):
    """设置界面（独立页面，替代弹窗）：默认输出文件夹 + 输出位置展示。"""

    def __init__(self, main):
        super().__init__()
        self._main = main
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 14, 14, 14)
        lay.setSpacing(10)

        lay.addWidget(_section('默认输出文件夹'))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit(main._root_out_dir)
        b_browse = QPushButton('浏览')
        b_browse.setObjectName('minorBtn')
        b_browse.clicked.connect(lambda: main._pick_root_dir(self.edit))
        row.addWidget(self.edit, 1)
        row.addWidget(b_browse)
        lay.addLayout(row)

        hint = QLabel('保存后将在该文件夹内自动创建「乱序混淆」「隐写水印」两个子文件夹，'
                      '两种模式的输出默认保存到对应子文件夹。')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #8a7f75; font-size: 11px;')
        lay.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        b_save = QPushButton('保存')
        b_save.setObjectName('okBtn')
        b_save.clicked.connect(self._save)
        btn_row.addWidget(b_save)
        lay.addLayout(btn_row)
        lay.addStretch(1)

    def _save(self):
        self._main._apply_root_dir(self.edit.text().strip())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('图片加密')
        self.setWindowIcon(QIcon(_resource_path('assets/app.ico')))
        self.resize(960, 660)
        self.setAcceptDrops(True)

        # 持久化：默认输出根目录（其下自动建 乱序混淆/隐写水印 两个子目录）
        self._settings = QSettings('ImageEncryption', 'ImageEncryption')
        saved = self._settings.value('root_out_dir', '')
        if saved:
            self._root_out_dir = str(saved)
        else:
            self._root_out_dir = self._default_root_dir()
        self.subdir('乱序混淆')
        self.subdir('隐写水印')

        self._build_ui()

    # ------------------------------------------------------------------
    # UI：顶栏 / 左栏(共用文件面板) / 右栏(配置切换) / 底栏
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ---- 顶栏 ----
        topbar = QWidget()
        topbar.setObjectName('topbar')
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(16, 9, 16, 9)
        tb.setSpacing(12)
        logo = QLabel('●')
        logo.setStyleSheet(f'color: {LANG_COLOR}; font-size: 15px;')
        name = QLabel('图片加密')
        name.setStyleSheet(
            'font-size: 15px; font-weight: 700; color: #f2ece5; letter-spacing: 3px;')
        tb.addWidget(logo)
        tb.addWidget(name)
        tb.addSpacing(10)

        self.mode_mixer = self._seg('乱序混淆', '像素乱序混淆：GC/RO/BS + 色彩反转')
        self.mode_watermark = self._seg('隐写水印', '盲水印嵌入/提取：文字或图片')
        self.mode_grp = QButtonGroup(self)
        self.mode_grp.setExclusive(True)
        for i, b in enumerate((self.mode_mixer, self.mode_watermark)):
            self.mode_grp.addButton(b)
            b.toggled.connect(lambda _on, idx=i: self._switch_mode(idx))
            # 从设置页点已选中的模式也能切回（toggled 对已选中按钮不触发）
            b.clicked.connect(lambda _=False, idx=i: self._switch_mode(idx))
            tb.addWidget(b)
        self.mode_mixer.setChecked(True)
        tb.addStretch(1)

        # ⚙ 设置
        gear = QPushButton('⚙')
        gear.setObjectName('gearBtn')
        gear.setCursor(Qt.PointingHandCursor)
        gear.setToolTip('设置：默认输出文件夹')
        gear.clicked.connect(self._open_settings)
        tb.addWidget(gear)

        self.dot = QLabel('●')
        self.dot.setStyleSheet(f'color: {OK_COLOR}; font-size: 12px;')
        tb.addWidget(self.dot)
        self.state_word = QLabel('就绪')
        self.state_word.setStyleSheet('color: #8a7f75; font-size: 12px;')
        tb.addWidget(self.state_word)
        v.addWidget(topbar)

        # ---- 中央：唯一 QSplitter（右栏宽度天然统一）----
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(10)
        split.setChildrenCollapsible(False)
        v.addWidget(split, 1)

        # ===== 左栏（两模式共用）：预览 + 文件缩略条 + 按钮行 =====
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 14, 6, 14)
        lv.setSpacing(10)

        self.preview = QLabel(EMPTY_HINT)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName('previewCanvas')
        self.preview.setMinimumHeight(220)
        lv.addWidget(self.preview, 1)

        self.info = QLabel('未导入文件')
        self.info.setStyleSheet('color: #8a7f75; font-size: 12px;')
        lv.addWidget(self.info)

        self.files = FileListWidget(self)
        self.files.itemClicked.connect(
            lambda item: self._show_preview(self.files.row(item)))
        lv.addWidget(self.files)

        fbtns = QHBoxLayout()
        fbtns.setSpacing(8)
        self.btn_choose = QPushButton('选择图片')
        self.btn_choose.setObjectName('importBtn')
        self.btn_choose.clicked.connect(self._browse_files)
        self.btn_remove = QPushButton('移除')
        self.btn_remove.setObjectName('minorBtn')
        self.btn_remove.clicked.connect(self._remove_files)
        self.btn_clear = QPushButton('清空')
        self.btn_clear.setObjectName('minorBtn')
        self.btn_clear.clicked.connect(self._clear_files)
        fbtns.addWidget(self.btn_choose, 1)
        fbtns.addWidget(self.btn_remove)
        fbtns.addWidget(self.btn_clear)
        lv.addLayout(fbtns)
        split.addWidget(left)

        # ===== 右栏：配置面板切换 =====
        self.pages = QStackedWidget()
        self.mixer_page = mixer.MixerConfig(self)
        self.watermark_page = watermark.WatermarkConfig(self)
        self.settings_page = SettingsPage(self)
        self.pages.addWidget(self.mixer_page)
        self.pages.addWidget(self.watermark_page)
        self.pages.addWidget(self.settings_page)
        split.addWidget(self.pages)
        split.setStretchFactor(0, 7)   # 右栏配置窄一些（约 1/3）
        split.setStretchFactor(1, 3)
        # 显式最小值取代 sizeHint 下限（setMinimumWidth(0) 会因 (0,0).isNull() 被忽略）
        self.pages.setMinimumWidth(1)
        self._split = split

        # 配置面板信号 → 顶栏状态点 / 底栏状态文字
        for page in (self.mixer_page, self.watermark_page):
            page.busy_sig.connect(self._set_busy)
            page.status_msg.connect(self._set_status)

        # ---- 底栏 ----
        bottombar = QWidget()
        bottombar.setObjectName('bottombar')
        bb = QHBoxLayout(bottombar)
        bb.setContentsMargins(16, 6, 16, 6)
        self.status = QLabel('就绪')
        self.status.setStyleSheet('color: #8a7f75; font-size: 12px;')
        self.status.setWordWrap(True)
        bb.addWidget(self.status)
        bb.addStretch(1)
        ver = QLabel(f'v{APP_VERSION}')
        ver.setStyleSheet('color: #5f564d; font-size: 11px;')
        bb.addWidget(ver)
        v.addWidget(bottombar)

    @staticmethod
    def _seg(text: str, tip: str) -> QPushButton:
        """顶栏模式段选按钮。"""
        b = QPushButton(text)
        b.setObjectName('segBtn')
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        return b

    # ------------------------------------------------------------------
    # 设置：默认输出文件夹（根目录，自动建两个子目录）
    # ------------------------------------------------------------------
    def _default_root_dir(self) -> str:
        """默认输出根目录：系统图片文件夹本身（「乱序混淆」「隐写水印」
        两个子目录直接建在其下）。"""
        pics = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.PicturesLocation)
        if not pics:
            pics = str(Path.home() / 'Pictures')
        return pics

    def subdir(self, name: str) -> Path:
        """返回根目录下指定子目录（不存在则创建）。"""
        d = Path(self._root_out_dir) / name
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def _open_settings(self):
        """右上角 ⚙ → 切换到设置页面。"""
        self.pages.setCurrentIndex(2)

    def _pick_root_dir(self, edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, '选择默认输出文件夹', edit.text())
        if folder:
            edit.setText(folder)

    def _apply_root_dir(self, path: str):
        """应用新根目录：建子目录、持久化、状态提示。"""
        if not path:
            QMessageBox.warning(self, '设置', '输出文件夹不能为空。')
            return
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, '设置', f'无法创建该文件夹：\n{e}')
            return
        self._root_out_dir = path
        self._settings.setValue('root_out_dir', path)
        for name in OUT_SUBDIRS:
            self.subdir(name)
        self._set_status(f'默认输出文件夹已保存：{path}'
                         f'（含「{"」「".join(OUT_SUBDIRS)}」子文件夹）')

    # ------------------------------------------------------------------
    # 模式切换 / 状态
    # ------------------------------------------------------------------
    def _switch_mode(self, idx: int):
        if not hasattr(self, 'pages'):
            return  # 构造期默认选中即触发，此时页面尚未建全
        self.pages.setCurrentIndex(idx)

    def _set_status(self, text: str):
        self.status.setText(text)

    def _set_busy(self, on: bool):
        """顶栏状态点：就绪=叶绿，处理中=琥珀。"""
        self.dot.setStyleSheet(
            f'color: {"#e8a13f" if on else OK_COLOR}; font-size: 12px;')
        self.state_word.setText('处理中…' if on else '就绪')

    # ------------------------------------------------------------------
    # 文件面板（两模式共用）：添加/移除/清空/预览
    # ------------------------------------------------------------------
    def file_paths(self) -> list[str]:
        return [self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())]

    def set_files(self, paths: list[str]):
        """处理对象跟随结果（如混淆连续加解密）后刷新列表。"""
        self.files.clear()
        self._add_files(paths)

    def _add_files(self, paths):
        """向缩略条追加文件（64px 图标 + 序号；重复路径跳过）。"""
        existing = {self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())}
        added = 0
        for p in paths:
            if p in existing:
                continue
            pix = QPixmap(p)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            if not pix.isNull():
                item.setIcon(QIcon(pix.scaled(
                    64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            item.setText(str(self.files.count() + 1))
            item.setSizeHint(QSize(76, 88))
            self.files.addItem(item)
            existing.add(p)
            added += 1
        self._sync_preview()
        return added

    def _sync_preview(self):
        """文件列表变化后：刷新预览与信息行（优先显示当前选中，否则第一张）。"""
        if self.files.count() == 0:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(EMPTY_HINT)
            self.info.setText('未导入文件')
            return
        row = self.files.currentRow()
        if row < 0:
            row = 0
        self.files.setCurrentRow(row)
        self._show_preview(row)

    def _show_preview(self, i: int):
        """左侧大预览显示第 i 个文件，随窗口尺寸自适应缩放。"""
        path = self.files.item(i).data(Qt.UserRole)
        pix = QPixmap(path)
        if pix.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText('(无法预览)')
            name = Path(path).name
            size_txt = ''
        else:
            w = max(1, self.preview.width() - 12)
            h = max(1, self.preview.height() - 12)
            self.preview.setPixmap(pix.scaled(
                w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            name = Path(path).name
            size_txt = f' · {pix.width()}×{pix.height()}'
        self.info.setText(f'{name}{size_txt} · 第 {i + 1}/{self.files.count()} 个')

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择图片（可多选）', '', IMAGE_FILTER)
        if paths:
            n = self._add_files(paths)
            self._set_status(f'已添加 {n} 张（共 {self.files.count()} 个文件）')

    def _remove_files(self):
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))
        self._sync_preview()

    def _clear_files(self):
        self.files.clear()
        self._sync_preview()

    # ------------------------------------------------------------------
    # 拖放（窗口级，进共用文件列表）
    # ------------------------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths:
            n = self._add_files(paths)
            self._set_status(f'已添加 {n} 张（共 {self.files.count()} 个文件）')

    def showEvent(self, e):
        super().showEvent(e)
        # setSizes 在 show 前不生效（显示时 QSplitter 按 sizeHint 重分配），首次显示后再定分栏
        if not getattr(self, '_sizes_done', False):
            self._sizes_done = True
            self._split.setSizes([640, 300])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.files.count():
            self._show_preview(
                self.files.currentRow() if self.files.currentRow() >= 0 else 0)

    def closeEvent(self, event):
        self.watermark_page.stop_threads()
        event.accept()


def main():
    app = QApplication(sys.argv)

    # 全局兜底：未捕获异常以弹窗呈现，避免静默闪退
    def _excepthook(exc_type, exc, tb):
        txt = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            QMessageBox.critical(None, "程序错误", txt)
        except Exception:
            sys.stderr.write(txt)
    sys.excepthook = _excepthook

    # Fusion 风格下 QSS 渲染最干净；配色由 DARK_QSS 全权负责
    app.setStyle('Fusion')
    app.setStyleSheet(DARK_QSS)

    # 引擎（cv2/blind_watermark）在 QApplication 就绪后再初始化，失败能弹窗
    try:
        watermark._init_engine()
    except Exception as e:
        try:
            Path("error.log").write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        QMessageBox.critical(
            None, "引擎初始化失败",
            f"无法初始化水印引擎：\n\n{e}\n\n详细错误已写入 error.log")
        sys.exit(2)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
