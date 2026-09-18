# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

# Backend source directory
backend_dir = os.path.join(os.path.dirname(os.path.abspath(SPEC)), '..', 'backend')
src_dir = os.path.join(backend_dir, 'src')

# Resolve native dependencies for THIS build interpreter.
#
# The packaging environment is a conda-style venv, where PyInstaller does not
# reliably collect the native libs that stdlib extension modules need at
# runtime (_sqlite3 -> sqlite3.dll, _ctypes -> ffi.dll, _ssl -> libssl). Without
# them the frozen backend dies on startup with "DLL load failed while importing
# _sqlite3 / _ctypes".
#
# Paths are DERIVED from the build interpreter (sys.base_prefix), never
# hardcoded to a user-specific directory, so the build stays reproducible.
def _first_existing(*candidates):
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


_base_prefix = getattr(sys, 'base_prefix', sys.prefix)
_lib_bin = os.path.join(_base_prefix, 'Library', 'bin')
_dlls_dir = os.path.join(_base_prefix, 'DLLs')
_win_sys32 = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'System32')

# Native shared libraries (conda keeps these under Library/bin).
_wanted_native = [
    'sqlite3.dll',
    'ffi.dll',
    'libcrypto-3-x64.dll',
    'libssl-3-x64.dll',
    # VC runtime — not always collected by PyInstaller when the build machine
    # has them on the system PATH (C:\Windows\System32).  A clean target
    # machine without the Visual C++ Redistributable would fail to start.
    'vcruntime140.dll',
    'vcruntime140_1.dll',
]
# CPython extension modules whose native deps must ship alongside them.
_wanted_ext = [
    '_ctypes.pyd',
    '_sqlite3.pyd',
    '_hashlib.pyd',
    '_ssl.pyd',
    '_decimal.pyd',
    '_lzma.pyd',
    '_bz2.pyd',
    '_elementtree.pyd',
    '_queue.pyd',
    '_socket.pyd',
    '_multiprocessing.pyd',
    '_asyncio.pyd',
    '_overlapped.pyd',
]

_extra_binaries = []
for _name in _wanted_native + _wanted_ext:
    _p = _first_existing(
        os.path.join(_lib_bin, _name),
        os.path.join(_dlls_dir, _name),
        os.path.join(_base_prefix, _name),
        os.path.join(_win_sys32, _name),
    )
    if _p:
        _extra_binaries.append((_p, '.'))
    else:
        print('backend.spec: WARNING native dependency not found:', _name)

print('backend.spec: extra binaries ->', [os.path.basename(b[0]) for b in _extra_binaries])

# Collect all source files
a = Analysis(
    [os.path.join(backend_dir, 'run.py')],
    pathex=[backend_dir, src_dir],
    binaries=_extra_binaries,
    datas=[
        (os.path.join(src_dir, 'routers'), 'src/routers'),
        (os.path.join(src_dir, 'engines'), 'src/engines'),
        (os.path.join(src_dir, 'models.py'), 'src'),
        (os.path.join(src_dir, 'database.py'), 'src'),
        (os.path.join(src_dir, 'config.py'), 'src'),
        (os.path.join(src_dir, 'auth.py'), 'src'),
        (os.path.join(src_dir, 'service.py'), 'src'),
        (os.path.join(src_dir, 'security.py'), 'src'),
        (os.path.join(src_dir, 'logging_config.py'), 'src'),
        (os.path.join(src_dir, 'entitlements.py'), 'src'),
        (os.path.join(src_dir, 'payment_service.py'), 'src'),
        (os.path.join(src_dir, 'migration_runner.py'), 'src'),
        (os.path.join(src_dir, 'migrations'), 'src/migrations'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'src.routers',
        'src.routers.documents',
        'src.routers.curriculum',
        'src.routers.generation',
        'src.routers.templates',
        'src.routers.settings',
        'src.routers.auth',
        'src.routers.payments',
        'src.routers.content_packs',
        'src.routers.ai_regeneration',
        'src.routers.platform_admin',
        'src.security',
        'src.engines',
        'src.engines.template_engine',
        'src.engines.generation_pipeline',
        'src.engines.docx_export',
        'src.engines.official_ges_template',
        'src.engines.official_ges_levels',
        'src.engines.xlsx_export',
        'src.engines.zip_export',
        'src.engines.pdf_export',
        'src.engines.ai_provider',
        'passlib',
        'passlib.hash',
        'jose',
        'jose.jwt',
        'bcrypt',
        'multipart',
        'multipart.multipart',
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
    [],
    exclude_binaries=True,
    name='schemeknit-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='schemeknit-backend',
)
