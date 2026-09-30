# -*- mode: python ; coding: utf-8 -*-
"""PORT-02C native onedir bundle spec (Windows x86-64).

Single COLLECT directory so the shell, worker, and qualifier executables
share one frozen dependency closure. The builder invokes:
    pyinstaller packaging/windows/athena-port02c.spec --distpath <bundle>/bin --workpath <tmp>
`datas` carries only the desktop shell UI assets; Python modules resolve via
pathex + PyInstaller import analysis. pytest/tests are excluded so test code
can never ship as a production runtime dependency.
"""
from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parents[1]
UI_DIR = REPO_ROOT / "ui"

# Hidden imports PyInstaller's static analysis cannot trace: domain/__init__
# and the historical-training-coverage facade resolve these underscore
# implementations through importlib at package-initialization time
# (proven by native CI: ModuleNotFoundError for the impl alias).
# Keep this list exact; do not broaden into package collection.
_HIDDEN_DOMAIN_IMPORTS = [
    "domain._historical_training_coverage_impl",
    "domain._historical_training_coverage_post_hardening",
    "domain._historical_training_coverage_row_issuance",
    "domain._historical_asof_features_impl",
]

_shared = dict(
    pathex=[str(REPO_ROOT)],
    binaries=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "_pytest", "tests", "tkinter", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

worker_a = Analysis(  # noqa: F821 - provided by PyInstaller at build time
    [str(REPO_ROOT / "runtime" / "worker_entry.py")],
    datas=[],
    hiddenimports=list(_HIDDEN_DOMAIN_IMPORTS),
    **_shared,
)
shell_a = Analysis(  # noqa: F821
    [str(REPO_ROOT / "run_desktop.py")],
    datas=[
        (str(UI_DIR / "index.html"), "ui"),
        (str(UI_DIR / "app.js"), "ui"),
        (str(UI_DIR / "styles.css"), "ui"),
    ],
    hiddenimports=list(_HIDDEN_DOMAIN_IMPORTS),
    **_shared,
)
qualify_a = Analysis(  # noqa: F821
    [str(REPO_ROOT / "scripts" / "qualify_port_02_native_runtime.py")],
    datas=[],
    hiddenimports=list(_HIDDEN_DOMAIN_IMPORTS),
    **_shared,
)

worker_pyz = PYZ(worker_a.pure, worker_a.zipped_data, cipher=None)  # noqa: F821
shell_pyz = PYZ(shell_a.pure, shell_a.zipped_data, cipher=None)  # noqa: F821
qualify_pyz = PYZ(qualify_a.pure, qualify_a.zipped_data, cipher=None)  # noqa: F821

worker_exe = EXE(  # noqa: F821
    worker_pyz,
    worker_a.scripts,
    [],
    exclude_binaries=True,
    name="athena-worker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="x86_64",
)
shell_exe = EXE(  # noqa: F821
    shell_pyz,
    shell_a.scripts,
    [],
    exclude_binaries=True,
    name="athena-shell",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="x86_64",
)
qualify_exe = EXE(  # noqa: F821
    qualify_pyz,
    qualify_a.scripts,
    [],
    exclude_binaries=True,
    name="athena-port02c-qualify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="x86_64",
)

coll = COLLECT(  # noqa: F821
    worker_exe,
    shell_exe,
    qualify_exe,
    worker_a.binaries,
    worker_a.zipfiles,
    worker_a.datas,
    shell_a.binaries,
    shell_a.zipfiles,
    shell_a.datas,
    qualify_a.binaries,
    qualify_a.zipfiles,
    qualify_a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="athena-bundle",
)
