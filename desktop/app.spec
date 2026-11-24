# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        (r'D:/YASEZ_HOME/projects/stem research ai/frontend/dist', 'app_root/frontend/dist'),
        (r'D:/YASEZ_HOME/projects/stem research ai/backend', 'app_root/backend'),
        (r'D:/YASEZ_HOME/projects/stem research ai/desktop/python-embed', 'python-embed'),
    ],
    hiddenimports=[
        'webview',
        'webview.platforms.edgechromium',
        'webview.platforms.mshtml',
        'webview.platforms.cef',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'sentence_transformers', 'transformers',
        'fastapi', 'uvicorn', 'starlette', 'sqlalchemy', 'pandas', 'numpy',
        'sklearn', 'scipy', 'sympy', 'pypdf', 'jose', 'passlib', 'reportlab',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='STEM Research Assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesigning_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='STEM Research Assistant',
)
