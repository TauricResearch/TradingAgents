# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# 获取当前目录
SCRIPT_PATH = os.path.dirname(os.path.abspath('a_share_gui_compatible.py'))

block_cipher = None

a = Analysis(
    ['a_share_gui_compatible.py'],
    pathex=[SCRIPT_PATH],
    binaries=[],
    datas=[
        ('GUI使用指南.md', '.'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
        'pandas',
        'requests',
        'urllib.request',
        'urllib.parse',
        'json',
        'threading',
        'datetime',
        'time',
        'random',
        'hashlib',
        'warnings',
        're',
        'os',
        'socket',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy.testing',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
        'scipy',
        'sklearn',
        'tensorflow',
        'torch',
        'cv2',
        'openpyxl',
        'xlrd',
        'xlwt',
        'docx',
        'pptx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 分散包模式 (onedir=True) - 生成目录而不是单个exe
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='A股智能分析系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件路径
)

# 收集所有文件到目录中
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='A股智能分析系统'
)