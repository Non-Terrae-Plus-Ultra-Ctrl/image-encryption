# -*- mode: python ; coding: utf-8 -*-
#
# 图片加密 2.0.0 onedir 打包配置（双模式：图片混淆 + 隐写水印）
# 用法： py -m PyInstaller --noconfirm --clean ImageEncryption.spec

# 过滤掉本程序用不到的二进制 DLL（沿用隐写水印 onedir 优化经验）
_UNUSED_BIN_SUBSTR = [
    'opencv_videoio_ffmpeg',   # OpenCV 视频编解码后端（本程序只处理图片）
    'opengl32sw',              # Qt 软件 OpenGL 渲染器（纯 QWidget 界面用不到）
    'Qt6Network.dll',          # Qt 网络模块（本程序不联网）
    'libcrypto-3.dll',         # OpenSSL 加密库（随 QtNetwork 拉入，不联网则不用）
    'libssl-3.dll',            # OpenSSL SSL 库（同上）
    'Qt6Svg.dll',              # SVG 渲染（本程序不使用 SVG）
    'qdirect2d.dll',           # Direct2D 平台插件（Windows 基本用 qwindows）
    'qtuiotouchplugin.dll',    # 触摸 UI 插件（桌面程序用不到）
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/app.ico', 'assets')],
    hiddenimports=['wm_core', 'mixer', 'watermark', 'scramble'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtSql', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtXml', 'PySide6.QtPrintSupport', 'PySide6.QtHelp', 'PySide6.QtDesigner', 'PySide6.QtUiTools', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtTest', 'PySide6.QtBluetooth', 'PySide6.QtSerialPort', 'PySide6.QtWebSockets', 'PySide6.QtWebChannel', 'PySide6.QtRemoteObjects', 'PySide6.QtSensors', 'PySide6.QtPositioning', 'PySide6.QtTextToSpeech', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtStateMachine', 'PySide6.QtScxml', 'PySide6.QtNfc', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DLogic', 'PySide6.QtCharts', 'PySide6.QtGraphs', 'numpy.testing', 'pytest', 'scipy', 'matplotlib', 'pandas', 'tkinter'],
    noarchive=False,
    optimize=0,
)

# 过滤无用二进制
a.binaries = [
    b for b in a.binaries
    if not any(sub in b[0] for sub in _UNUSED_BIN_SUBSTR)
]

# 只保留中文（文件名含 zh）的 Qt 翻译，删除其余所有语言
a.datas = [
    d for d in a.datas
    if not (d[0].endswith('.qm') and 'zh' not in d[0])
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ImageEncryption',
    icon='assets/app.ico',
    version='version_info.txt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # onedir 不用 UPX，保持最速启动
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ImageEncryption',
)
