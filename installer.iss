; 图片加密 2.0.9 安装包脚本 (Inno Setup 6)
; 编译: ISCC.exe installer.iss
; 产物: D:\系统文件\桌面\测试\图片加密\图片加密_2.0.9.exe

#define MyAppName "图片加密"
#define MyAppVersion "2.0.9"
#define MyAppExeName "ImageEncryption.exe"

[Setup]
AppId={{B7F3A2C1-9D4E-4F8B-A5C6-3E1D2B7A9F04}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
DefaultDirName={autopf}\图片加密
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
SetupIconFile=assets\app.ico
OutputDir=D:\系统文件\桌面\测试\图片加密
OutputBaseFilename=图片加密_2.0.9
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; 语言使用默认英文向导（界面文字与应用名仍为中文）
; 如需简体中文向导，请将 ChineseSimplified.isl 放入 Inno Setup 的 Languages 目录后启用：
; [Languages]
; Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"

[Files]
Source: "dist\ImageEncryption\ImageEncryption.exe"; DestDir: "{app}"; Flags: ignoreversion
; onedir 内部目录（_internal 等所有依赖文件）
Source: "dist\ImageEncryption\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
