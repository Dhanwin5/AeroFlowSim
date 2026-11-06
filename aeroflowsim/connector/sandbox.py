# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The workspace: the one folder the AI connector may read and write (safety rule 1).

An AI names things by plain text: a project name ("my nozzle") or a file path relative to the workspace
("inputs/wall.csv"). Every such text is checked here before any file is touched. Refused:
  * absolute paths, drive letters, UNC paths (\\\\server\\share), "~";
  * ".." anywhere, empty parts;
  * Windows reserved names (CON, NUL, COM1, ...) and characters Windows forbids;
  * anything that, after following symbolic links / junctions, lies outside the workspace;
  * any path where some part is itself a link or junction (a link could later be re-pointed).
"""

import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from aeroflowsim.project import SUFFIX, is_project

RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
MAX_NAME = 120


class SandboxError(ValueError):
    """A path or name the connector refuses (the message says why)."""


def _is_link(path: Path) -> bool:
    """A symbolic link or a Windows junction (junctions are not symlinks to Python before 3.12)."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


class Workspace:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    def ensure(self):
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- checks ----------------------------------------------------------------------------------

    def parts_of(self, text) -> list[str]:
        """The parts of a relative path typed by the AI, or SandboxError."""
        if not isinstance(text, str) or not text.strip():
            raise SandboxError("A name or a path inside the workspace is needed.")
        text = text.strip()
        win, posix = PureWindowsPath(text), PurePosixPath(text)
        if win.drive or win.root or posix.root or text.startswith(("\\\\", "//", "~")):
            raise SandboxError(f"'{text}': only paths inside the workspace are allowed (no absolute, drive or "
                               "network paths).")
        parts = [p for p in re.split(r"[\\/]", text)]
        for part in parts:
            if part in ("", ".", ".."):
                raise SandboxError(f"'{text}': '..', '.' and empty path parts are not allowed.")
            if BAD_CHARS.search(part) or part != part.rstrip(" ."):
                raise SandboxError(f"'{text}': the name '{part}' has characters Windows does not allow.")
            if part.split(".")[0].lower() in RESERVED:
                raise SandboxError(f"'{text}': '{part}' is a reserved Windows device name.")
            if len(part) > MAX_NAME:
                raise SandboxError(f"'{text}': a name is longer than {MAX_NAME} characters.")
        return parts

    def inside(self, path: Path) -> Path:
        """path, after checking that it and every folder above it up to the root is no link and lies inside."""
        path = Path(path)
        current = path
        while True:
            if current == self.root:
                break
            if current.exists() and _is_link(current):
                raise SandboxError(f"'{path.relative_to(self.root)}' goes through a link or junction; refused.")
            if current.parent == current:
                raise SandboxError("The path is outside the workspace.")
            current = current.parent
        real = Path(os.path.realpath(path))
        if real != self.root and self.root not in real.parents:
            raise SandboxError("The path is outside the workspace.")
        return path

    def path(self, text) -> Path:
        """A file or folder path typed by the AI -> checked absolute path inside the workspace."""
        return self.inside(self.root.joinpath(*self.parts_of(text)))

    def project_path(self, name) -> Path:
        """Folder of the project called `name` ("my nozzle" or "my nozzle.afsproj"), directly in the workspace."""
        parts = self.parts_of(name)
        if len(parts) != 1:
            raise SandboxError(f"'{name}': a project name, not a path (projects live directly in the workspace).")
        base = parts[0][: -len(SUFFIX)] if parts[0].lower().endswith(SUFFIX) else parts[0]
        if not base:
            raise SandboxError("A project name is needed.")
        return self.inside(self.root / f"{base}{SUFFIX}")

    def existing_project(self, name) -> Path:
        folder = self.project_path(name)
        if not is_project(folder):
            raise SandboxError(f"There is no project '{name}' in the workspace (list_projects shows them).")
        return folder

    def projects(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(p for p in self.root.iterdir() if p.name.endswith(SUFFIX) and not _is_link(p) and is_project(p))
