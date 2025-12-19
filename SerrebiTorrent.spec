# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Ship all OpenSSL 1.1 variants (some envs load the generic name)
binaries = [
    ('libcrypto-1_1-x64.dll', '.'),
    ('libcrypto-1_1.dll', '.'),
    ('libssl-1_1-x64.dll', '.'),
    ('libssl-1_1.dll', '.'),
]

# Bundle the static web UI folder
datas = [
    ('web_static', 'web_static'),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SerrebiTorrent',
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
)
