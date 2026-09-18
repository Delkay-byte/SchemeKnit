#!/usr/bin/env python3
"""
TeachFlow Backend Packaging Script
Packages the FastAPI backend as a standalone executable using PyInstaller.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def get_spec_content(params):
    return f"""# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

# Find sqlite3 DLL
sqlite_dlls = []
for search_dir in [r'{params["conda_dlls"]}', r'{params["venv_dlls"]}']:
    if os.path.isdir(search_dir):
        for f in os.listdir(search_dir):
            if 'sqlite' in f.lower():
                sqlite_dlls.append((os.path.join(search_dir, f), '.'))

a = Analysis(
    [r'{params["run_py"]}'],
    pathex=[r'{params["backend_dir"]}', r'{params["src_dir"]}'],
    binaries=sqlite_dlls,
    datas=[
        (r'{params["routers_dir"]}', 'src/routers'),
        (r'{params["engines_dir"]}', 'src/engines'),
        (r'{params["migrations_dir"]}', 'src/migrations'),
        (r'{params["models_py"]}', 'src'),
        (r'{params["database_py"]}', 'src'),
        (r'{params["config_py"]}', 'src'),
        (r'{params["auth_py"]}', 'src'),
        (r'{params["service_py"]}', 'src'),
        (r'{params["logging_config_py"]}', 'src'),
        (r'{params["entitlements_py"]}', 'src'),
        (r'{params["payment_service_py"]}', 'src'),
        (r'{params["migration_runner_py"]}', 'src'),
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
        'uvicorn.lifespan.off',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets.wsproto_impl',
        'src',
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
        'src.engines',
        'src.engines.template_engine',
        'src.engines.generation_pipeline',
        'src.engines.docx_export',
        'src.engines.xlsx_export',
        'src.engines.zip_export',
        'src.engines.pdf_export',
        'src.engines.ai_provider',
        'passlib',
        'passlib.hash',
        'passlib.handlers.bcrypt',
        'jose',
        'jose.jwt',
        'jose.constants',
        'jose.exceptions',
        'jose.backends',
        'jose.backends.cryptography_backend',
        'bcrypt',
        'multipart',
        'multipart.multipart',
        'multipart.exceptions',
        'aiosqlite',
        'aiofiles',
        'aiofiles.os',
        'aiofiles.tempfile',
        'aiofiles.threadpool',
        'aiofiles.implementations',
        'docxtpl',
        'docxtpl.templating',
        'docxtpl.exceptions',
        'openpyxl',
        'openpyxl.cell',
        'openpyxl.workbook',
        'openpyxl.styles',
        'pandas',
        'pandas._libs',
        'pandas._libs.tslibs',
        'structlog',
        'structlog._config',
        'structlog._loggers',
        'structlog._processors',
        'structlog._stdlib',
        'structlog._types',
        'structlog.contextvars',
        'structlog.dev',
        'structlog.easy',
        'structlog.exceptions',
        'structlog.logger',
        'structlog.stdlib',
        'structlog.threadlocal',
    ],
    hookspath=[],
    hooksconfig={{}},
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
    name='teachflow-backend',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='teachflow-backend',
)
"""

def main():
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent / 'backend'
    src_dir = backend_dir / 'src'
    py312_dir = script_dir / 'py312'
    
    # Use the standalone Python 3.12 (has all Windows DLLs)
    python_exe = py312_dir / 'python.exe'
    if not python_exe.exists():
        python_exe = Path(sys.executable)
    
    print("=" * 50)
    print("TeachFlow Backend Packaging")
    print("=" * 50)
    print(f"Python: {python_exe}")
    print()
    
    # Clean previous build
    print("[1/4] Cleaning previous builds...")
    for d in [script_dir / 'build', script_dir / 'dist']:
        if d.exists():
            shutil.rmtree(d)
    print("    [OK] Cleaned")
    print()
    
    # Install PyInstaller if needed
    print("[2/4] Checking PyInstaller...")
    result = subprocess.run([str(python_exe), '-m', 'PyInstaller', '--version'], 
                           capture_output=True, text=True)
    if result.returncode == 0:
        print(f"    [OK] PyInstaller {result.stdout.strip()} found")
    else:
        print("    Installing PyInstaller...")
        subprocess.run([str(python_exe), '-m', 'pip', 'install', 'pyinstaller'], check=True)
        print("    [OK] PyInstaller installed")
    print()
    
    # Create PyInstaller spec
    print("[3/4] Creating PyInstaller spec...")
    
    # Find sqlite3 DLL locations
    conda_dlls = Path(sys.prefix) / 'Library' / 'bin'
    venv_dlls = py312_dir
    
    params = {
        "run_py": str(backend_dir / 'run.py'),
        "src_main": str(src_dir / 'main.py'),
        "backend_dir": str(backend_dir),
        "src_dir": str(src_dir),
        "conda_dlls": str(conda_dlls),
        "venv_dlls": str(venv_dlls),
        "routers_dir": str(src_dir / 'routers'),
        "engines_dir": str(src_dir / 'engines'),
        "migrations_dir": str(src_dir / 'migrations'),
        "models_py": str(src_dir / 'models.py'),
        "database_py": str(src_dir / 'database.py'),
        "config_py": str(src_dir / 'config.py'),
        "auth_py": str(src_dir / 'auth.py'),
        "service_py": str(src_dir / 'service.py'),
        "logging_config_py": str(src_dir / 'logging_config.py'),
        "entitlements_py": str(src_dir / 'entitlements.py'),
        "payment_service_py": str(src_dir / 'payment_service.py'),
        "migration_runner_py": str(src_dir / 'migration_runner.py'),
    }
    
    spec_content = get_spec_content(params)
    spec_file = script_dir / 'teachflow-backend.spec'
    spec_file.write_text(spec_content)
    print("    [OK] Spec file created")
    print()
    
    # Run PyInstaller
    print("[4/4] Building backend with PyInstaller...")
    result = subprocess.run([
        str(python_exe), '-m', 'PyInstaller',
        str(spec_file),
        '--clean',
        '--noconfirm',
        '--workpath', str(script_dir / 'build'),
        '--distpath', str(script_dir / 'dist'),
    ], cwd=str(script_dir))
    
    if result.returncode != 0:
        print("    [ERROR] PyInstaller failed")
        sys.exit(1)
    
    # Verify build
    built_exe = script_dir / 'dist' / 'teachflow-backend' / 'teachflow-backend.exe'
    if built_exe.exists():
        size_mb = built_exe.stat().st_size / (1024 * 1024)
        print(f"    [OK] Backend packaged successfully ({size_mb:.1f} MB)")
    else:
        print("    [ERROR] Backend build failed - exe not found")
        sys.exit(1)
    
    # Clean up spec file and build artifacts
    if spec_file.exists():
        spec_file.unlink()
    for d in [script_dir / 'build']:
        if d.exists():
            shutil.rmtree(d)
    
    print()
    print("=" * 50)
    print("Backend packaging complete!")
    print("=" * 50)
    print()
    print(f"Backend: {built_exe}")
    print()

if __name__ == '__main__':
    main()
