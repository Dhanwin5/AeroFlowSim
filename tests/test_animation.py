# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Flow animation (aeroflowsim/post/animation.py): recording during a run, storage next to run.npz, playback logic
and GIF export. Walk-through of the user's next actions: run -> frames; Stop / max iterations then Run again ->
frames appended; Start from scratch -> a new set; recording off -> no frames; change an input -> out of date;
re-mesh -> the old frames are not shown on the new mesh; old project without frames -> None."""

import numpy as np
import pytest

from aeroflowsim.cli import main
from aeroflowsim.post.animation import (ANIMATION_FILE, MAX_AUTO_FRAMES, FrameRecorder, Playback, export_animation,
                                        frame_label, load_animation, project_animation)
from aeroflowsim.post.solution import Solution
from aeroflowsim.project import Project, run_project

SMALL = {"mesh_preset": "Custom", "nx": 30, "nr": 6, "tol": 1e-12}


# ---- recorder -----------------------------------------------------------------------------------------

def _run(recorder, n, cells=3):
    recorder.add(0, 0.0, np.zeros((4, cells)))
    for it in range(1, n + 1):
        if recorder.due(it):
            recorder.add(it, 0.0, np.full((4, cells), float(it)))
    return recorder.animation(n, 0.0, np.full((4, cells), float(n)))


@pytest.mark.parametrize("n", [7, 100, 333, 5000, 123457])
def test_automatic_recording_keeps_50_to_100_evenly_spread_frames(n):
    anim = _run(FrameRecorder(every=0, n_cells=3), n)
    assert anim.iterations[0] == 0 and anim.iterations[-1] == n
    assert anim.n <= MAX_AUTO_FRAMES + 1
    if n > MAX_AUTO_FRAMES:
        assert anim.n >= MAX_AUTO_FRAMES // 2
    inner = anim.iterations[1:-1]
    assert np.all(inner % anim.every == 0) and np.all(np.diff(anim.iterations) > 0)
    assert np.allclose(anim.fields["rho"][:, 0], anim.iterations)        # each frame holds its own state
    assert anim.fields["p"].dtype == np.float32


def test_fixed_interval_and_rewind_after_a_cfl_back_off():
    rec = FrameRecorder(every=10, n_cells=2)
    for it in (0, 10, 20, 30):
        rec.add(it, 0.0, np.full((4, 2), it))
    rec.rewind(20)                       # the solver went back to its last good state (iteration 20)
    rec.add(30, 0.0, np.full((4, 2), 31.0))
    anim = rec.animation(35, 0.0, np.full((4, 2), 35.0))
    assert list(anim.iterations) == [0, 10, 20, 30, 35] and anim.fields["rho"][3, 0] == 31.0


def test_playback_logic():
    pb = Playback(n=3, fps=20, loop=False)
    assert pb.interval_ms == 50
    pb.play()
    assert [pb.tick(), pb.tick()] == [1, 2] and not pb.playing      # stops on the last frame without loop
    pb.play()                                                        # Play at the end starts again
    assert pb.index == 0 and pb.playing
    pb.loop = True
    pb.seek(2)
    assert pb.tick() == 0 and pb.playing                             # loop: back to the first frame
    pb.step(-5)
    assert pb.index == 0 and not pb.playing
    pb.set_count(1)
    pb.play()
    assert not pb.playing                                           # one frame: nothing to play


# ---- runs of a project --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def first_run(tmp_path_factory):
    folder = tmp_path_factory.mktemp("anim") / "nozzle.afsproj"
    project = Project.create("nozzle_axi", folder, {**SMALL, "max_iter": 40})
    out = run_project(project, fresh=True)
    return folder, out


def test_a_run_records_frames_next_to_its_result(first_run):
    folder, out = first_run
    project = Project.open(folder)
    assert (project.results_dir / ANIMATION_FILE).is_file()
    anim = project_animation(project, mesh=project.load_mesh())
    assert anim.iterations[0] == 0 and anim.iterations[-1] == out.result.iterations == 40
    final = anim.frame(anim.n - 1)
    assert np.allclose(final["p"], out.result.fields["p"].values, rtol=1e-6)    # last frame = the final result
    assert frame_label(anim, 0).startswith("Iteration 0")


def test_recording_does_not_change_the_result(first_run, tmp_path):
    folder, out = first_run
    project = Project.create("nozzle_axi", tmp_path / "off.afsproj", {**SMALL, "max_iter": 40})
    project.set_post("animation", {"record": False, "every": 0})
    off = run_project(project, fresh=True)
    assert not (project.results_dir / ANIMATION_FILE).exists()
    assert project_animation(project, mesh=project.load_mesh()) is None
    for k in ("rho", "u", "v", "p"):
        assert np.array_equal(off.result.fields[k].values, out.result.fields[k].values)


def test_continue_appends_and_start_from_scratch_clears(first_run, tmp_path):
    import shutil
    folder = tmp_path / "copy.afsproj"
    shutil.copytree(first_run[0], folder)
    project = Project.open(folder)
    before = project_animation(project, mesh=project.load_mesh())
    project.values["max_iter"] = 70
    project.save()
    run_project(project)                                     # Run again: carries on from iteration 40
    anim = project_animation(project, mesh=project.load_mesh())
    assert anim.iterations[-1] == 70
    assert list(anim.iterations[:before.n]) == list(before.iterations)          # the earlier frames are kept
    run_project(project, fresh=True)                         # Start from scratch: a new set from iteration 0
    fresh = project_animation(project, mesh=project.load_mesh())
    assert fresh.iterations[0] == 0 and fresh.iterations[-1] == 70
    assert len(set(fresh.iterations)) == fresh.n


def test_fixed_every_n_and_out_of_date_and_remesh(first_run, tmp_path):
    import shutil
    folder = tmp_path / "every.afsproj"
    shutil.copytree(first_run[0], folder)
    project = Project.open(folder)
    project.set_post("animation", {"record": True, "every": 10})
    project.save()
    run_project(project, fresh=True)
    anim = project_animation(project, mesh=project.load_mesh())
    assert list(anim.iterations) == [0, 10, 20, 30, 40]
    project.values["p0"] = float(project.params()["p0"]) * 1.1      # change an input
    assert project.status("results") == "outdated"          # the frames belong to the old result: out of date too
    project.values["nx"] = 34                                # re-mesh: the frames are never shown on the new mesh
    from aeroflowsim.project import build_project_mesh
    mesh = build_project_mesh(project)
    assert project_animation(project, mesh=mesh) is None


def test_old_project_without_frames(first_run, tmp_path):
    import shutil
    folder = tmp_path / "old.afsproj"
    shutil.copytree(first_run[0], folder)
    (folder / "results" / ANIMATION_FILE).unlink()
    project = Project.open(folder)
    project.post.pop("animation", None)                      # a project.yaml from before the feature
    assert project_animation(project, mesh=project.load_mesh()) is None
    assert project.run_extras()["animation"]["record"] is True
    assert main(["export", str(folder), "--animation", str(tmp_path / "x.gif")]) == 2


def test_gif_export_and_command_line(first_run, tmp_path):
    folder, _ = first_run
    project = Project.open(folder)
    anim = load_animation(project.results_dir)
    sol = Solution.from_project(project)
    path = export_animation(tmp_path / "flow.gif", anim, sol, "M", size=(3.0, 2.0))
    from PIL import Image
    with Image.open(path) as im:
        assert im.n_frames == anim.n
    assert main(["export", str(folder), "--animation", str(tmp_path / "p.gif"), "--field", "p", "--fps", "5",
                 "--per-frame-range"]) == 0
    assert (tmp_path / "p.gif").stat().st_size > 1000
    with pytest.raises(ValueError):
        export_animation(tmp_path / "none.gif", None)


def test_sod_snapshots_play_back_as_a_1d_animation(tmp_path):
    project = Project.create("sod_shock_tube", tmp_path / "sod.afsproj", {"n_cells": 100})
    run_project(project)
    anim = project_animation(project, mesh=project.load_mesh())
    assert anim is not None and not anim.steady and anim.n >= 2 and len(anim.x) == anim.fields["rho"].shape[1]
    assert frame_label(anim, 1).startswith("t = ")
    assert main(["export", str(project.folder), "--animation", str(tmp_path / "sod.gif"), "--field", "rho"]) == 0
