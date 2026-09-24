# -*- coding: utf-8 -*-
"""mixer.py — 「图片加密」的乱序混淆配置面板（v2.0.1 重构）。

与 v2.0.0 的差别：
- 只负责右栏配置与处理逻辑，文件列表/预览由主窗口共用面板提供
- 单张保存：弹保存框，默认位置定位到 根目录\\乱序混淆
- 批量输出：不再弹目录选择，直接输出到 根目录\\乱序混淆（状态栏显示）
功能逻辑不变：三种加密方式 + 色彩反转、命名参数编码、解密自动提取、序号续排。
算法复用 scramble.py（与 13123123.xyz 逐字节兼容）。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scramble  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from PySide6.QtCore import Qt, QCoreApplication, Signal  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QLabel, QPushButton, QCheckBox, QButtonGroup,
    QSpinBox, QLineEdit, QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog,
    QMessageBox, QProgressBar,
)

EXT = {'png': '.png', 'webp': '.webp', 'jpg': '.jpg'}
METHOD_CODE = {'gilbert': 'GC', 'fastest': 'RO', 'block': 'BS'}  # 输出命名/外观缩写


class UserCancelled(Exception):
    """用户拒绝了「块不整除不可逆」的警告。"""


class MixerConfig(QWidget):
    """乱序混淆配置面板：加密方式/输出格式/色彩反转/密钥/分块 + 加解密。"""

    status_msg = Signal(str)   # 状态消息 → 主窗口底栏
    busy_sig = Signal(bool)    # 忙碌状态 → 主窗口顶栏状态点

    def __init__(self, main):
        super().__init__()
        self._main = main
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        rv = QVBoxLayout(self)
        rv.setContentsMargins(6, 14, 14, 14)
        rv.setSpacing(6)

        rv.addWidget(self._section('加密方式'))
        seg = QWidget()
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        self.btn_gilbert = self._seg('吉尔伯特', '吉尔伯特曲线-GC')
        self.btn_fastest = self._seg('最速混淆', '快速混淆-RO')
        self.btn_block = self._seg('分块', '分块大小-BS')
        self.method_grp = QButtonGroup(self)
        self.method_grp.setExclusive(True)
        for b in (self.btn_gilbert, self.btn_fastest, self.btn_block):
            self.method_grp.addButton(b)
            b.toggled.connect(self._sync_params)  # toggled：用户点击/程序化设置都触发
            sl.addWidget(b, 1)
        self.btn_gilbert.setChecked(True)
        rv.addWidget(seg)
        rv.addSpacing(10)

        rv.addWidget(self._section('输出格式'))
        fseg = QWidget()
        fl = QHBoxLayout(fseg)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)
        self.btn_png = self._seg('PNG', 'PNG（无损，可精确还原）')
        self.btn_jpg = self._seg('JPG', 'JPG（有损 95）')
        self.btn_webp = self._seg('WEBP', 'WEBP（无损）')
        self.format_grp = QButtonGroup(self)
        self.format_grp.setExclusive(True)
        for b, k in ((self.btn_png, 'png'), (self.btn_jpg, 'jpg'), (self.btn_webp, 'webp')):
            self.format_grp.addButton(b)
            b.setProperty('fmt', k)
            fl.addWidget(b, 1)
        self.btn_png.setChecked(True)
        rv.addWidget(fseg)
        rv.addSpacing(10)

        # 色彩反转
        self.xor_check = QCheckBox('色彩反转')
        self.xor_check.setObjectName('xorCheck')
        self.xor_check.setCursor(Qt.PointingHandCursor)
        self.xor_check.setToolTip('R/G/B 通道按位取反，可叠加二次混淆')
        rv.addWidget(self.xor_check)
        rv.addSpacing(10)

        # 密钥行
        self.key_row = QWidget()
        kr = QHBoxLayout(self.key_row)
        kr.setContentsMargins(0, 0, 0, 0)
        kr.setSpacing(10)
        kr.addWidget(QLabel('密钥'))
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText('可为空')
        kr.addWidget(self.key_edit, 1)
        rv.addWidget(self.key_row)

        # 分块行
        self.block_row = QWidget()
        br = QVBoxLayout(self.block_row)
        br.setContentsMargins(0, 0, 0, 0)
        br.setSpacing(4)
        brow = QHBoxLayout()
        brow.setSpacing(10)
        brow.addWidget(QLabel('分块大小'))
        self.spin_bw = QSpinBox()
        self.spin_bh = QSpinBox()
        for s in (self.spin_bw, self.spin_bh):
            s.setRange(1, 4096)
            s.setValue(1)
            s.setButtonSymbols(QSpinBox.NoButtons)  # 去上下调整按钮，直接键入数值
        brow.addWidget(self.spin_bw)
        brow.addWidget(QLabel('×'))
        brow.addWidget(self.spin_bh)
        brow.addStretch(1)
        br.addLayout(brow)
        self.block_hint = QLabel('长和宽像素数必须整除')
        self.block_hint.setWordWrap(True)
        self.block_hint.setStyleSheet('color: #8a7f75; font-size: 11px;')
        br.addWidget(self.block_hint)
        rv.addWidget(self.block_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        rv.addWidget(self.progress)

        obtn = QHBoxLayout()
        obtn.setSpacing(8)
        self.btn_enc = QPushButton('加 密')
        self.btn_enc.setObjectName('encBtn')
        self.btn_enc.clicked.connect(lambda: self._process('encrypt'))
        self.btn_dec = QPushButton('解 密')
        self.btn_dec.setObjectName('decBtn')
        self.btn_dec.clicked.connect(lambda: self._process('decrypt'))
        obtn.addWidget(self.btn_enc, 1)
        obtn.addWidget(self.btn_dec, 1)
        rv.addLayout(obtn)

        # 日志（批量逐张结果 / 自动提取明细，同水印页）
        rv.addSpacing(10)
        rv.addWidget(self._section('日志'))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        rv.addWidget(self.log, 1)

        self._sync_params()

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

    def _busy(self, on: bool):
        self.busy_sig.emit(on)

    def _sync_params(self):
        # 分块大小仅「分块」显示；密钥「最速混淆」不显示（其余方式显示）
        if not hasattr(self, 'block_row'):
            return  # 构造期默认选中即触发，此时控件尚未建全
        method = self._current_method()
        self.block_row.setVisible(method == 'block')
        self.key_row.setVisible(method != 'fastest')

    def _current_method(self):
        if self.btn_fastest.isChecked():
            return 'fastest'
        if self.btn_block.isChecked():
            return 'block'
        return 'gilbert'

    def _current_format(self):
        for b in (self.btn_png, self.btn_jpg, self.btn_webp):
            if b.isChecked():
                return b.property('fmt')
        return 'png'

    # ---------- 命名 ----------
    @staticmethod
    def _has_wm_part(stem: str) -> bool:
        """源文件名是否含水印元信息段（全数字段：带序号 4 段 / 去序号 3 段）。
        与 watermark._parse_wm_name 的段格式一致，避免循环导入故本地判定；
        混淆段第二位恒为 GC/RO/BS 字母，不会被误认。"""
        for part in stem.split('_'):
            segs = part.split('-')
            if len(segs) in (3, 4) and all(s.isdigit() for s in segs):
                return True
        return False

    def _out_name(self, idx: int, fmt: str, src_stem: str = '') -> str:
        """输出自动命名（参数编码进文件名，供解密自动提取）。
        源文件名带水印段 → 双段叠加：源段原样在前（序号保持第一位），
        新混淆段去序号，如 1-7-9-96_GC-密钥-CI.png，全名仅一个序号。
        普通图 → 现状模板 NNN-方式[-分块w×h][-密钥][-CI]。"""
        method = self._current_method()
        blk = f'-{self.spin_bw.value()}x{self.spin_bh.value()}' if method == 'block' else ''
        key = self.key_edit.text() if method != 'fastest' else ''
        # 密钥仅当可安全入名时编码；恰为 'CI' 会与反转标志歧义，跳过
        key_part = f'-{key}' if key and key != 'CI' and self._key_ok_for_name(key) else ''
        ci_part = '-CI' if self.xor_check.isChecked() else ''
        body = f'{METHOD_CODE[method]}{blk}{key_part}{ci_part}'
        prefix = f'{src_stem}_' if src_stem and self._has_wm_part(src_stem) else ''
        name = body if prefix else f'{idx:03d}-{body}'  # 叠加时新段去序号
        return f'{prefix}{name}{EXT[fmt]}'

    @staticmethod
    def _key_ok_for_name(key: str) -> bool:
        """密钥可安全写入文件名（无 Windows 非法字符、首尾无空格、非 . ..）。"""
        return (key == key.strip() and not set(key) & set('\\/:*?"<>|')
                and key not in {'.', '..'} and '\x00' not in key)

    @staticmethod
    def _parse_name(p):
        """从文件名自动提取混淆参数。文件名可含多个元信息段（段间用 '_' 连接，
        如 001-GC-密钥_1-7-9-96.png = 混淆段_水印段）——分段扫描第一个可识别
        的混淆段；兼容旧格式 001-GC.png / 001-GC-CI.png（无 '_' 时整名即一段）。"""
        stem = Path(p).stem
        for part in stem.split('_'):
            m = MixerConfig._parse_mix_part(part)
            if m is not None:
                return m
        return None

    @staticmethod
    def _parse_mix_part(stem):
        """解析单个混淆段，两种形态：
        - 带序号：NNN-方式[-分块w×h][-密钥][-CI]（如 001-GC-密钥-CI）
        - 去序号：方式[-分块w×h][-密钥][-CI]（双段叠加里的新段，如 GC-密钥-CI）
        水印段全数字，第二位无 GC/RO/BS，不会被误认；不匹配返回 None。"""
        xor = False
        if stem.endswith('-CI'):
            xor = True
            stem = stem[:-3]
        parts = stem.split('-')
        code_map = {'GC': 'gilbert', 'RO': 'fastest', 'BS': 'block'}
        if parts and parts[0].isdigit():
            parts = parts[1:]  # 剥离序号（两种形态在此归一）
        if not parts or parts[0] not in code_map:
            return None
        method = code_map[parts[0]]
        rest = parts[1:]
        block = None
        if method == 'block' and rest and re.fullmatch(r'\d+x\d+', rest[0]):
            a, b = rest[0].split('x')
            block = (int(a), int(b))
            rest = rest[1:]
        key = '' if method == 'fastest' else '-'.join(rest)
        return {'method': method, 'key': key, 'block': block, 'xor': xor}

    @staticmethod
    def _next_seq(outdir: Path) -> int:
        """输出目录中 NNN-* 已有文件的最大序号 +1（序号自动续排，不与旧文件撞名）。"""
        mx = 0
        pat = re.compile(r'^(\d+)-')
        if outdir.is_dir():
            for f in outdir.iterdir():
                m = pat.match(f.name)
                if m:
                    mx = max(mx, int(m.group(1)))
        return mx + 1

    @staticmethod
    def _unique_path(p: Path) -> Path:
        """已存在时追加 (1)(2)…，避免覆盖（序号续排后的极端兜底）。"""
        if not p.exists():
            return p
        for i in range(1, 1000):
            q = p.with_name(f'{p.stem} ({i}){p.suffix}')
            if not q.exists():
                return q
        return p

    # ---------- 处理 ----------
    def _process(self, mode: str):
        files = [Path(p) for p in self._main.file_paths()]
        if not files:
            QMessageBox.information(self, '提示', '请先导入图片')
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QCoreApplication.processEvents()
        self._busy(True)
        try:
            fmt = self._current_format()
            bw, bh = self.spin_bw.value(), self.spin_bh.value()
            method = self._current_method()
            key = self.key_edit.text()
            xor = self.xor_check.isChecked()
            label = '加密' if mode == 'encrypt' else '解密'
            outdir = self._main.subdir('乱序混淆')  # 输出目录由全局设置决定
            self.log.append(f'开始{label}：方式={METHOD_CODE[method]} '
                            f'密钥={key or "空"} 色彩反转={"开" if xor else "关"}')

            # ---- 解密：从文件名自动提取参数（NNN-方式[-分块][-密钥][-CI]）----
            parsed = [None] * len(files)
            if mode == 'decrypt':
                parsed = [self._parse_name(f) for f in files]
                n_fail = sum(1 for x in parsed if x is None)
                if n_fail:
                    if len(files) == 1:
                        ret = QMessageBox.question(
                            self, '自动提取失败',
                            '未能从文件名自动提取参数（文件名可能被修改）。\n'
                            '是否仍使用当前界面参数解密？',
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        if ret != QMessageBox.Yes:
                            self.log.append(f'自动提取失败：{files[0].name}（已取消，请手动选择参数后重试）')
                            self._status('已取消（自动提取失败，请手动选择参数后重试）')
                            return
                        self.log.append(f'自动提取失败：{files[0].name}，按当前界面参数解密')
                    else:
                        self.log.append(f'自动提取：{len(files) - n_fail} 张成功，'
                                        f'{n_fail} 张将按当前界面参数解密')
            if len(files) == 1 and parsed[0]:
                method = parsed[0]['method']
                key = parsed[0]['key']
                if parsed[0]['block']:
                    bw, bh = parsed[0]['block']
                xor = parsed[0]['xor']

            if len(files) == 1:
                self._single(mode, fmt, method, key, (bw, bh), xor, label, outdir)
                return

            # ---- 批量：直接输出到 乱序混淆 目录，不弹选择框 ----
            self._block_warned = False
            if method == 'block':
                nondiv = []
                for f in files:
                    try:
                        w0, h0 = PILImage.open(str(f)).size
                        if w0 % bw or h0 % bh:
                            nondiv.append(f.name)
                    except Exception:  # noqa: BLE001
                        pass  # 读不了的由 _run_one 报错，这里只管可读尺寸
                if nondiv:
                    ret = QMessageBox.warning(
                        self, '不整除',
                        f'块大小 {bw}×{bh} 不能整除以下图片（边缘像素不可逆，解密无法精确还原）：\n' +
                        '\n'.join(nondiv[:8]) + (f' 等 {len(nondiv)} 张' if len(nondiv) > 8 else '') +
                        '\n\n继续吗？',
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if ret != QMessageBox.Yes:
                        self._status('已取消（块大小不整除图像）')
                        return
                self._block_warned = True  # 批量已一次确认，_run_one 不再逐张弹窗
            total = len(files)
            seq = self._next_seq(outdir)  # ★序号续排：目录已有 001/002 则从 003 起
            self.progress.setVisible(True)
            self.progress.setRange(0, total)
            self.progress.setValue(0)
            results: list[Path] = []
            errors: list[tuple[str, str]] = []
            for i, src in enumerate(files):
                if mode == 'decrypt' and parsed[i]:  # 每张按各自文件名参数解密
                    pm = parsed[i]['method']
                    pk = parsed[i]['key']
                    pblk = parsed[i]['block'] or (bw, bh)
                    px = parsed[i]['xor']
                else:
                    pm, pk, pblk, px = method, key, (bw, bh), xor
                # 加密时源文件名带水印段则保留在前（先做的在前）；解密输出为新还原图，不保留
                src_stem = src.stem if mode == 'encrypt' else ''
                out = self._unique_path(outdir / self._out_name(seq + i, fmt, src_stem))
                try:
                    results.append(self._run_one(src, mode, fmt, pm, pk, pblk, px, out))
                    self.log.append(f'[{i + 1}/{total}] 已生成 {out.name}')
                except UserCancelled:
                    self.log.append(f'[{i + 1}/{total}] 已取消（块大小不整除）')
                    break
                except Exception as ex:  # noqa: BLE001
                    errors.append((src.name, str(ex)))
                    self.log.append(f'[{i + 1}/{total}] 跳过 {src.name}: {ex}')
                self.progress.setValue(i + 1)
                QCoreApplication.processEvents()

            self.progress.setVisible(False)
            if results:
                self._main.set_files([str(r) for r in results])  # ★处理对象跟随结果
            if errors:
                self.log.append(f'{label}完成 {len(results)}/{total}，失败 {len(errors)} 张')
                self._status(f'{label}完成 {len(results)}/{total}，'
                             f'失败 {len(errors)}：' +
                             '；'.join(f'{n}: {e}' for n, e in errors))
                QMessageBox.warning(self, '部分失败', '\n'.join(
                    f'{n}: {e}' for n, e in errors))
            else:
                self.log.append(f'{label}完成 {len(results)}/{total} 张 → {outdir}')
                self._status(f'{label}完成 {len(results)}/{total} 张 → {outdir}')
        except UserCancelled:
            self.log.append('已取消（块大小不整除图像）')
            self._status('已取消（块大小不整除图像）')
        except Exception as ex:  # noqa: BLE001
            self.log.append(f'出错：{ex}')
            self._status(f'出错：{ex}')
            QMessageBox.critical(self, '处理失败', str(ex))
        finally:
            self._busy(False)
            QApplication.restoreOverrideCursor()

    def _single(self, mode, fmt, method, key, block, xor, label, outdir):
        files = [Path(p) for p in self._main.file_paths()]
        src = files[0]
        seq = self._next_seq(outdir)  # 默认名从目录已有序号续排
        # 加密时源文件名带水印段则保留在前（先做的在前）；解密输出为新还原图，不保留
        default = outdir / self._out_name(seq, fmt, src.stem if mode == 'encrypt' else '')
        path, _ = QFileDialog.getSaveFileName(
            self, '保存', str(default),
            'PNG 图片 (*.png);;WEBP 图片 (*.webp);;JPEG 图片 (*.jpg)')
        if not path:
            self.log.append('已取消保存')
            self._status('已取消保存')
            return
        out = self._unique_path(Path(path))
        self._run_one(src, mode, fmt, method, key, block, xor, out)
        self._main.set_files([str(out)])   # ★处理对象跟随结果图
        self.log.append(f'{label}完成（{method}，色彩反转={xor}）：{out}')
        self._status(f'{label}完成（{method}，色彩反转={xor}）：{out}')

    def _run_one(self, src: Path, mode: str, fmt: str, method: str, key: str,
                 block, xor: bool, out: Path) -> Path:
        img, data = scramble.load_rgba(str(src))
        w, h = img.size
        if method == 'block' and (w % block[0] or h % block[1]) and not getattr(self, '_block_warned', False):
            self._block_warned = True
            ret = QMessageBox.warning(
                self, '不整除',
                f'{block[0]}×{block[1]} 不能整除图片 {w}×{h}，边缘像素将不可逆，继续吗？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                raise UserCancelled
        func = scramble.encrypt_rgba if mode == 'encrypt' else scramble.decrypt_rgba
        result = func(bytes(data), w, h, method, key, block, xor)
        scramble.save_rgba(result, w, h, str(out), fmt)
        return out
