# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The one-click Claude Desktop extension of AeroFlowSim (an .mcpb file), one per operating system.

    python tools/build_mcpb.py                  writes dist/AeroFlowSim-<version>-claude-<windows|macos|linux>.mcpb
    python tools/build_mcpb.py --out files      ... into another folder (the release job of installer.yml)

What it is: a zip file with manifest.json (MCPB format, github.com/modelcontextprotocol/mcpb, MANIFEST.md) and the
icon. It contains NO program code: it tells Claude Desktop to start the AeroFlowSim program the user installed with the
normal installer, as  <program> mcp --extension --workspace <folder>. Claude Desktop shows two settings on install,
both filled in already: the program (the installer's default place on this operating system) and the workspace folder
(Documents/AeroFlowSim Projects). So the user double-clicks the file and presses Install.
"""

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Where the installers put the program (tools/installer/aeroflowsim.iss: {localappdata}\Programs\AeroFlowSim; the dmg:
# drag to /Applications; the AppImage: wherever the user saves it - ~/Applications is the AppImage convention).
PROGRAMS = {
    "windows": ("win32", "${HOME}/AppData/Local/Programs/AeroFlowSim/AeroFlowSim.exe"),
    "macos": ("darwin", "/Applications/AeroFlowSim.app/Contents/MacOS/AeroFlowSim"),
    "linux": ("linux", "${HOME}/Applications/AeroFlowSim-x86_64.AppImage"),
}

DESCRIPTION = ("Let Claude set up, mesh, run and report AeroFlowSim CFD projects (nozzles, propulsion, external "
               "aerodynamics) on your own computer.")
LONG_DESCRIPTION = (
    "AeroFlowSim is a free, open-source CFD program for nozzle and propulsion aerodynamics. With this extension Claude "
    "can list templates, gases and shapes, create projects, set inputs with units, import geometry, mesh, check, run "
    "in the background, read the results with the software's own validity verdict, make pictures, compare runs, "
    "export and write the report.\n\n"
    "Everything runs on this computer: no network connection, nothing is uploaded. Claude can use only the "
    "workspace folder chosen below, never deletes or overwrites anything, never runs its own code, and asks before "
    "long runs.\n\n"
    "Needs the AeroFlowSim program (free installer: github.com/Dhanwin5/AeroFlowSim/releases).")


def manifest(platform: str) -> dict:
    from aeroflowsim import __version__
    from aeroflowsim.api import TOOLS, Api
    os_name, program = PROGRAMS[platform]
    tools = []
    for name in TOOLS:
        doc = (getattr(Api, name).__doc__ or "").strip().splitlines()
        tools.append({"name": name, "description": (doc[0] if doc else name)[:200]})
    return {
        "manifest_version": "0.3",
        "name": "aeroflowsim",
        "display_name": "AeroFlowSim",
        "version": __version__,
        "description": DESCRIPTION,
        "long_description": LONG_DESCRIPTION,
        "author": {"name": "Dhanwin Mehta", "url": "https://github.com/Dhanwin5"},
        "repository": {"type": "git", "url": "https://github.com/Dhanwin5/AeroFlowSim"},
        "homepage": "https://github.com/Dhanwin5/AeroFlowSim",
        "documentation": "https://github.com/Dhanwin5/AeroFlowSim/blob/main/docs/user_guide.md",
        "support": "https://github.com/Dhanwin5/AeroFlowSim/issues",
        "icon": "icon.png",
        "license": "GPL-3.0-or-later",
        "keywords": ["cfd", "aerodynamics", "nozzle", "propulsion", "simulation", "engineering"],
        "server": {
            "type": "binary",
            "entry_point": "${user_config.program}",
            "mcp_config": {
                "command": "${user_config.program}",
                "args": ["mcp", "--extension", "--workspace", "${user_config.workspace}"],
                "env": {},
            },
        },
        "tools": tools,
        "user_config": {
            "program": {
                "type": "file",
                "title": "AeroFlowSim program",
                "description": "The installed AeroFlowSim program. Already filled in if you installed it in the "
                               "default place; change it only if you chose another folder.",
                "default": program,
                "required": True,
            },
            "workspace": {
                "type": "directory",
                "title": "Workspace folder",
                "description": "The only folder Claude may use for AeroFlowSim projects, imports and exports.",
                "default": "${DOCUMENTS}/AeroFlowSim Projects",
                "required": True,
            },
        },
        "compatibility": {"platforms": [os_name]},
    }


def icon_png() -> bytes:
    """The AeroFlowSim icon on a square 256 x 256 transparent canvas."""
    from PIL import Image
    src = Image.open(ROOT / "assets" / "icon.png").convert("RGBA")
    src.thumbnail((256, 256))
    canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    canvas.paste(src, ((256 - src.width) // 2, (256 - src.height) // 2), src)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def build(platform: str, out_dir: Path) -> Path:
    from aeroflowsim import __version__
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"AeroFlowSim-{__version__}-claude-{platform}.mcpb"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(platform), indent=2))
        z.writestr("icon.png", icon_png())
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "dist"))
    args = parser.parse_args(argv)
    for platform in PROGRAMS:
        print(f"Wrote {build(platform, Path(args.out))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
