# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build the installer of this operating system: PyInstaller one-folder build, then

    Windows   dist/AeroFlowSim-<version>-setup.exe      (Inno Setup, if installed)
    macOS     dist/AeroFlowSim-<version>-macOS-<arm64|x86_64>.dmg   (AeroFlowSim.app in a disk image, hdiutil)
    Linux     dist/AeroFlowSim-<version>-<arch>.AppImage            (one file; appimagetool, if found)

    python tools/build_installer.py              build it
    python tools/build_installer.py --smoke      also run the smoke test of the built program

macOS and Linux builds are made by GitHub Actions (.github/workflows/installer.yml); they are not code-signed either
(macOS: right-click > Open the first time; see docs/user_guide.md).

Build tools (not runtime dependencies): PyInstaller (pip install pyinstaller) and Inno Setup 6 (iscc.exe).
The one-folder build keeps Qt / PySide6 (LGPL) as separate, replaceable DLLs. THIRD_PARTY_LICENSES.txt is
generated from the installed packages and shipped with the program (Help > About shows it). The installer installs
per user (no administrator rights), adds a Start-menu shortcut, associates .afsproj files (the file
project.afsproj in every project folder) and has an uninstaller. It is not code-signed: Windows SmartScreen
warns on first start ("More info" > "Run anyway"); see docs/user_guide.md.
"""

import argparse
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
EXAMPLES = ROOT / "examples"


def third_party_licenses(path):
    """One text file with the name, version, licence and licence text (where shipped) of every installed package."""
    lines = ["AeroFlowSim bundles the following third-party software. Each is distributed under its own licence.",
             "AeroFlowSim itself is GPL-3.0-or-later (LICENSE). Qt (PySide6) is LGPL-3.0: this program uses it as",
             "separate DLLs in the installation folder, which may be replaced by compatible versions.", ""]
    for dist in sorted(metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = dist.metadata["Name"]
        if not name or name.lower() in ("aeroflowsim", "pyinstaller", "pyinstaller-hooks-contrib", "pip"):
            continue
        lic = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
        classifiers = [c.split("::")[-1].strip() for c in (dist.metadata.get_all("Classifier") or [])
                       if c.startswith("License")]
        lines.append("=" * 100)
        lines.append(f"{name} {dist.version}")
        lines.append(f"Licence: {(lic.splitlines()[0] if lic else '') or ', '.join(classifiers) or 'see the package'}")
        home = dist.metadata.get("Home-page") or ""
        if home:
            lines.append(f"Home page: {home}")
        for f in dist.files or []:
            if any(k in f.name.upper() for k in ("LICENSE", "LICENCE", "COPYING")) and f.suffix.lower() in ("", ".txt",
                                                                                                         ".md", ".rst"):
                try:
                    text = Path(f.locate()).read_text(encoding="utf-8", errors="replace")
                    lines += ["", text.strip()[:20000]]
                    break
                except OSError:
                    pass
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


def pyinstaller():
    from aeroflowsim import __version__
    third_party_licenses(ROOT / "THIRD_PARTY_LICENSES.txt")
    data = [(ROOT / "cases", "cases"), (ROOT / "assets", "assets"), (ROOT / "LICENSE", "."),
            (ROOT / "THIRD_PARTY_LICENSES.txt", "."), (ROOT / "README.md", "."), (ROOT / "CITATION.cff", "."),
            (ROOT / "validation" / "report.md", "validation")]
    data += [(f, "docs") for f in (ROOT / "docs").glob("*.md")]
    data += [(ROOT / "docs" / "tutorials", "docs/tutorials")]
    from PIL import Image
    icon = BUILD / "aeroflowsim.ico"
    BUILD.mkdir(exist_ok=True)
    Image.open(ROOT / "assets" / "icon.png").save(icon, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    if EXAMPLES.is_dir():
        data.append((EXAMPLES, "examples"))
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "AeroFlowSim",
            "--distpath", str(DIST), "--workpath", str(BUILD), "--specpath", str(BUILD),
            "--collect-all", "aeroflowsim", "--collect-all", "gmsh", "--collect-all", "pyvista",
            "--collect-all", "pyvistaqt", "--collect-all", "numba", "--collect-all", "llvmlite",
            "--collect-submodules", "vtkmodules", "--collect-data", "matplotlib",
            "--exclude-module", "streamlit", "--exclude-module", "plotly", "--exclude-module", "pytest",
            "--exclude-module", "tkinter"]
    if sys.platform == "darwin":
        icns = BUILD / "aeroflowsim.icns"
        Image.open(ROOT / "assets" / "icon.png").save(icns)
        icon = icns
        args += ["--osx-bundle-identifier", "org.aeroflowsim.AeroFlowSim"]
    if icon.is_file() and sys.platform != "linux":
        args += ["--icon", str(icon)]
    for src, dst in data:
        if src.exists():
            args += ["--add-data", f"{src}{';' if sys.platform == 'win32' else ':'}{dst}"]
    args.append(str(ROOT / "tools" / "installer" / "aeroflowsim_app.py"))
    subprocess.run(args, check=True, cwd=ROOT)
    # cases are found next to the package (aeroflowsim/discovery.py: the package folder's parent)
    print(f"Built {DIST / 'AeroFlowSim'} (version {__version__})")
    return DIST / "AeroFlowSim"


def executable(folder):
    """The program inside the build: the .exe (Windows), the binary inside the .app (macOS) or the folder (Linux)."""
    if sys.platform == "win32":
        return folder / "AeroFlowSim.exe"
    if sys.platform == "darwin":
        return DIST / "AeroFlowSim.app" / "Contents" / "MacOS" / "AeroFlowSim"
    return folder / "AeroFlowSim"


def arch():
    import platform
    m = platform.machine().lower()
    return {"amd64": "x86_64", "aarch64": "arm64"}.get(m, m)


def dmg():
    """macOS: AeroFlowSim.app and a link to /Applications in a compressed disk image (drag to install)."""
    from aeroflowsim import __version__
    app = DIST / "AeroFlowSim.app"
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    subprocess.run(["ditto", str(app), str(stage / "AeroFlowSim.app")], check=True)     # keeps links and attributes
    (stage / "Applications").symlink_to("/Applications")
    out = DIST / f"AeroFlowSim-{__version__}-macOS-{arch()}.dmg"
    out.unlink(missing_ok=True)
    subprocess.run(["hdiutil", "create", "-volname", f"AeroFlowSim {__version__}", "-srcfolder", str(stage),
                    "-ov", "-format", "UDZO", str(out)], check=True)
    print(f"Disk image: {out} ({out.stat().st_size / 1024**2:.0f} MB)")
    return out


DESKTOP = """[Desktop Entry]
Type=Application
Name=AeroFlowSim
Comment=CFD for nozzle and propulsion aerodynamics
Exec=AeroFlowSim %f
Icon=aeroflowsim
Categories=Science;Education;Engineering;
Terminal=false
"""

APPRUN = """#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/aeroflowsim/AeroFlowSim" "$@"
"""


def appimage(folder):
    """Linux: the program folder as one AppImage file (AppDir + appimagetool); None if appimagetool is missing."""
    from aeroflowsim import __version__
    tool = shutil.which("appimagetool") or (str(BUILD / "appimagetool") if (BUILD / "appimagetool").is_file() else None)
    if tool is None:
        print("appimagetool not found: only the program folder was built.")
        return None
    appdir = BUILD / "AeroFlowSim.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(folder, appdir / "usr" / "lib" / "aeroflowsim", symlinks=True)
    (appdir / "aeroflowsim.desktop").write_text(DESKTOP, encoding="utf-8")
    shutil.copy(ROOT / "assets" / "icon.png", appdir / "aeroflowsim.png")
    run = appdir / "AppRun"
    run.write_text(APPRUN, encoding="utf-8")
    run.chmod(0o755)
    out = DIST / f"AeroFlowSim-{__version__}-{arch()}.AppImage"
    env = {**__import__("os").environ, "ARCH": arch(), "APPIMAGE_EXTRACT_AND_RUN": "1"}
    subprocess.run([tool, str(appdir), str(out)], check=True, env=env)
    print(f"AppImage: {out} ({out.stat().st_size / 1024**2:.0f} MB)")
    return out


def inno(folder):
    from aeroflowsim import __version__
    iscc = shutil.which("iscc") or next((str(p) for p in (
        Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe", Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"))
        if p.is_file()), None)
    script = ROOT / "tools" / "installer" / "aeroflowsim.iss"
    if iscc is None:
        print("Inno Setup (iscc.exe) not found: only the program folder was built.")
        return None
    subprocess.run([iscc, f"/DAppVersion={__version__}", f"/DSourceDir={folder}", f"/DOutputDir={DIST}", str(script)],
                   check=True)
    setup = DIST / f"AeroFlowSim-{__version__}-setup.exe"
    print(f"Installer: {setup} ({setup.stat().st_size / 1024**2:.0f} MB)")
    return setup


def smoke(folder):
    """--version, a headless run of the Sod case, and the GUI starts and closes."""
    exe = executable(folder)
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=120)
    print("version:", out.stdout.strip() or out.stderr.strip())
    assert __import__("aeroflowsim").__version__ in out.stdout, "--version printed nothing"
    tmp = BUILD / "smoke"
    shutil.rmtree(tmp, ignore_errors=True)
    r = subprocess.run([str(exe), "run", "sod_shock_tube", "--out", str(tmp)], capture_output=True, text=True,
                       timeout=600)
    print("run sod: exit", r.returncode)
    assert r.returncode in (0, 2) and (tmp / "summary.yaml").is_file(), r.stdout[-2000:] + r.stderr[-2000:]
    # a 2D run: the Numba kernels must load in the frozen program (first run compiles, then the cache is used)
    r2 = subprocess.run([str(exe), "run", "external_2d", "--set", "shape=Wedge", "--set", "max_iter=50", "--out",
                         str(tmp / "2d")], capture_output=True, text=True, timeout=900)
    print("run 2D:", next((line for line in r2.stdout.splitlines() if line.startswith("Solver:")), "no solver line"))
    assert "Numba kernels" in r2.stdout, r2.stdout[-2000:] + r2.stderr[-2000:]
    env = {**__import__("os").environ, "AEROFLOWSIM_QUIT_AFTER_MS": "4000"}
    g = subprocess.run([str(exe)], timeout=180, env=env)
    print("GUI start/close: exit", g.returncode)
    assert g.returncode == 0
    print("Smoke test passed")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)
    folder = DIST / "AeroFlowSim" if args.skip_build else pyinstaller()
    if args.smoke:
        smoke(folder)
    if sys.platform == "win32":
        inno(folder)
    elif sys.platform == "darwin":
        dmg()
    else:
        appimage(folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
