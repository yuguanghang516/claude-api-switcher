# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
生成独立的 Claude API Switcher V4.2.0 可执行文件
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/app_icon.ico', 'assets')],
    hiddenimports=[
        'customtkinter',
        'darkdetect',
        'keyring',
        'keyring.backends.Windows',
        'requests',
        'flask',
        'jinja2',
        'werkzeug',
        'click',
        'itsdangerous',
        'markupsafe',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Claude API Switcher V4.2.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
    version=None,
    product_name='Claude API Switcher V4.2.0',
    product_version='4.2.0',
    company_name='',
    copyright='',
    description='Claude Code API environment and local AI gateway manager',
)
