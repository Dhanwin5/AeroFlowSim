# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Entry point of the installed program (AeroFlowSim.exe on Windows, AeroFlowSim.app on macOS, the AppImage on Linux;
built by tools/build_installer.py).

    AeroFlowSim.exe                          start the desktop GUI
    AeroFlowSim.exe "My nozzle.afsproj"      open a project in the GUI; double-clicking the file project.afsproj inside
                                             a project folder does this (file association made by the installer)
    AeroFlowSim.exe run <case or project>    the command line (also: list, report, export, snapshot, --version)

The program is built without a console window; for command-line use it attaches to the console it was started
from, so its output appears there.
"""

import sys

COMMANDS = {"run", "list", "report", "export", "snapshot", "gui", "--version", "-h", "--help"}


def _attach_console():
    if sys.platform != "win32" or sys.stdout is not None:   # output already goes somewhere (a pipe or a console)
        return
    import ctypes
    if ctypes.windll.kernel32.AttachConsole(-1):          # the console of the parent (cmd / PowerShell)
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]   # macOS Finder may add a process serial number
    if args and args[0] in COMMANDS:
        _attach_console()
        from aeroflowsim.cli import main as cli
        return cli(args)
    from aeroflowsim.gui.app import main as gui
    project = None
    if args:
        from pathlib import Path
        p = Path(args[0])
        project = str(p.parent if p.is_file() else p)      # project.afsproj / project.yaml inside the folder
    return gui(["aeroflowsim"] + ([project] if project else []))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()                      # the background helper process of the GUI
    sys.exit(main())
