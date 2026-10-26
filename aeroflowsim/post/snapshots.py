# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Solution snapshots: named copies of a project's result, to compare with or go back to.

    results/snapshots/<name>/run.npz        the result (compressed)
    results/snapshots/<name>/mesh.npz       the mesh it was computed on (compressed)
    results/snapshots/<name>/snapshot.yaml  when it was saved, the run record (fingerprint, iterations, status)

A user saves "baseline", changes inputs, runs, and then compares the new result with the baseline (side by side,
difference) or restores the baseline as the current result. Restoring also restores the snapshot's mesh and the
run record, so the workflow strip shows honestly whether the restored result matches the current inputs.
"""

import datetime
import shutil
from pathlib import Path

import numpy as np
import yaml

SNAPSHOT_DIR = "snapshots"
SIZE_WARNING_BYTES = 500 * 1024**2     # warn when a project folder grows beyond 500 MB


def snapshots_dir(project) -> Path:
    return project.results_dir / SNAPSHOT_DIR


def snapshot_path(project, name) -> Path:
    path = snapshots_dir(project) / safe_name(name) / "run.npz"
    if not path.is_file():
        raise ValueError(f"There is no snapshot called '{name}'.")
    return path


def safe_name(name) -> str:
    """A folder name for a snapshot name (letters, digits, space, - and _ kept)."""
    text = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in str(name)).strip()
    if not text:
        raise ValueError("A snapshot needs a name.")
    return text


def _compress(source, target):
    """Copy an .npz file as a compressed .npz (same arrays, same names)."""
    with np.load(source, allow_pickle=False) as data:
        arrays = {k: data[k] for k in data.files}
    np.savez_compressed(target, **arrays)


def list_snapshots(project) -> list:
    """[{"name", "saved", "iterations", "status", "size"}] sorted by the time saved."""
    out = []
    folder = snapshots_dir(project)
    if not folder.is_dir():
        return out
    for sub in folder.iterdir():
        meta_file = sub / "snapshot.yaml"
        if not (sub / "run.npz").is_file() or not meta_file.is_file():
            continue
        meta = yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
        size = sum(f.stat().st_size for f in sub.iterdir() if f.is_file())
        out.append({"name": meta.get("name", sub.name), "saved": meta.get("saved", ""),
                    "iterations": (meta.get("run") or {}).get("iterations"), "status": (meta.get("run") or {}).get("status"),
                    "size": size, "folder": sub})
    return sorted(out, key=lambda s: s["saved"])


def save_snapshot(project, name, overwrite=False) -> Path:
    """Save the current result (and its mesh) as a named snapshot."""
    source = project.results_dir / "run.npz"
    if not source.is_file():
        raise ValueError("There is no result to save as a snapshot: run the project first.")
    folder = snapshots_dir(project) / safe_name(name)
    if folder.exists():
        if not overwrite:
            raise ValueError(f"A snapshot called '{name}' already exists.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    _compress(source, folder / "run.npz")
    mesh_file = project.mesh_dir / "mesh.npz"
    if mesh_file.is_file():
        _compress(mesh_file, folder / "mesh.npz")
    meta = {"name": str(name), "saved": datetime.datetime.now().isoformat(timespec="seconds"),
            "run": dict(project.steps.get("run") or {}), "mesh": dict(project.steps.get("mesh") or {})}
    (folder / "snapshot.yaml").write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return folder


def rename_snapshot(project, old, new):
    src = snapshots_dir(project) / safe_name(old)
    dst = snapshots_dir(project) / safe_name(new)
    if not src.is_dir():
        raise ValueError(f"There is no snapshot called '{old}'.")
    if dst.exists():
        raise ValueError(f"A snapshot called '{new}' already exists.")
    src.rename(dst)
    meta_file = dst / "snapshot.yaml"
    meta = yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
    meta["name"] = str(new)
    meta_file.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")


def delete_snapshot(project, name):
    """Delete a snapshot (the GUI asks for confirmation first)."""
    folder = snapshots_dir(project) / safe_name(name)
    if not folder.is_dir():
        raise ValueError(f"There is no snapshot called '{name}'.")
    shutil.rmtree(folder)


def snapshot_mesh(project, name):
    """The mesh a snapshot was computed on (aeroflowsim.mesh.Mesh), or the project's current mesh if it has none."""
    from aeroflowsim.mesh import Mesh
    path = snapshots_dir(project) / safe_name(name) / "mesh.npz"
    return Mesh.load(path) if path.is_file() else project.load_mesh()


def restore_snapshot(project, name):
    """Make a snapshot the current result again (with its mesh and run record). The current result is replaced:
    the GUI offers to save it as a snapshot first."""
    folder = snapshots_dir(project) / safe_name(name)
    if not (folder / "run.npz").is_file():
        raise ValueError(f"There is no snapshot called '{name}'.")
    meta = yaml.safe_load((folder / "snapshot.yaml").read_text(encoding="utf-8")) or {}
    project.results_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(folder / "run.npz", project.results_dir / "run.npz")
    if (folder / "mesh.npz").is_file():
        from aeroflowsim.mesh import Mesh
        from aeroflowsim.vtk import mesh_cell_data, write_vtu
        mesh = Mesh.load(folder / "mesh.npz")
        project.mesh_dir.mkdir(parents=True, exist_ok=True)
        mesh.save(project.mesh_dir / "mesh.npz")
        write_vtu(project.mesh_dir / "mesh.vtu", mesh, mesh_cell_data(mesh))
        if meta.get("mesh"):
            project.steps["mesh"] = dict(meta["mesh"])
    if meta.get("run"):
        project.steps["run"] = dict(meta["run"])
    project.save()


def folder_size(path) -> int:
    """Total size of the files in a folder [bytes]."""
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())


def size_text(n) -> str:
    for unit in ("bytes", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def size_warning(project, limit=SIZE_WARNING_BYTES) -> str:
    """'' or a plain-language warning when the project folder is larger than the limit."""
    size = folder_size(project.folder)
    if size <= limit:
        return ""
    return (f"The project folder is {size_text(size)} (more than {size_text(limit)}). Delete snapshots you no longer "
            "need (Results > Snapshots) to make it smaller.")
