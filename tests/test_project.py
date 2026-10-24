# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Projects: create, save, open, duplicate, share; up-to-date status; results saved exactly; command line."""

import shutil

import numpy as np
import pytest
import yaml

from aeroflowsim.cli import main
from aeroflowsim.discovery import find_cases, load_case
from aeroflowsim.engine import run_case
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.project import (PROJECT_FILE, Project, build_project_mesh, folder_for, is_project,
                                 run_project)
from aeroflowsim.result_io import load_run, save_run


def test_folder_name_from_a_typed_name(tmp_path):
    assert folder_for("My Nozzle", tmp_path) == tmp_path / "My Nozzle.afsproj"
    assert folder_for("a/b:c", tmp_path).name == "a_b_c.afsproj"
    assert folder_for("x.afsproj", tmp_path).name == "x.afsproj"
    with pytest.raises(ValueError):
        folder_for("  ", tmp_path)


@pytest.mark.parametrize("template", sorted(find_cases()[0]))
def test_create_open_round_trip_for_every_template(tmp_path, template):
    project = Project.create(template, tmp_path / "P.afsproj")
    assert is_project(project.folder)
    for sub in ("geometry", "mesh", "results"):
        assert (project.folder / sub).is_dir()
    for p in project.case.parameters():          # example files copied in, stored relative
        if p.type == "file":
            assert project.values[p.name].startswith("geometry/")
            assert (project.folder / project.values[p.name]).is_file()
    again = Project.open(project.folder)
    assert again.values == project.values and again.warnings == []
    assert again.case.name == template
    assert again.status("mesh") == "none"
    assert again.status("run") == ("none" if again.case.has_solver else "disabled")


def test_save_marks_clean_and_keeps_changed_inputs(tmp_path):
    project = Project.create("nozzle_axi", tmp_path / "P.afsproj")
    project.set_value("d_exit", 0.001)
    assert project.dirty
    project.save()
    assert not project.dirty
    assert Project.open(project.folder).values["d_exit"] == 0.001


def test_duplicate_and_save_as(tmp_path):
    project = Project.create("nozzle_axi", tmp_path / "A.afsproj")
    build_project_mesh(project)
    copy = project.duplicate(tmp_path / "B.afsproj")
    assert copy.status("mesh") == "ok"                       # mesh and its record came along
    assert (copy.folder / "mesh" / "mesh.npz").is_file()
    assert project.folder == tmp_path / "A.afsproj"
    project.save_as(tmp_path / "C.afsproj")
    assert project.folder == tmp_path / "C.afsproj" and is_project(tmp_path / "A.afsproj")
    with pytest.raises(ValueError):
        project.duplicate(tmp_path / "B.afsproj")             # never overwrite


def test_a_zipped_copy_elsewhere_reproduces_the_inputs_and_mesh(tmp_path):
    project = Project.create("nozzle_axi", tmp_path / "mine" / "P.afsproj")
    project.set_value("geometry_source", "Custom profile (CSV)")
    project.save()
    build_project_mesh(project)
    archive = shutil.make_archive(str(tmp_path / "shared"), "zip", project.folder.parent, project.folder.name)
    shutil.unpack_archive(archive, tmp_path / "friend")
    theirs = Project.open(tmp_path / "friend" / "P.afsproj")
    assert theirs.status("mesh") == "ok"                       # same inputs, same file contents
    assert np.array_equal(theirs.load_mesh().nodes, project.case.build_mesh(theirs.params()).nodes)


def test_upstream_change_marks_downstream_outdated(tmp_path):
    project = Project.create("quasi1d_nozzle", tmp_path / "P.afsproj", values={"n_cells": 60})
    run_project(project)
    assert project.statuses() == {"geometry": "ok", "mesh": "ok", "setup": "ok", "run": "ok", "results": "ok"}
    project.set_value("p_back", 2.0e5)                         # setup input: only the run is outdated
    assert project.status("mesh") == "ok" and project.status("run") == "outdated"
    project.set_value("p_back", defaults(project.case.parameters())["p_back"])
    assert project.status("run") == "ok"                       # back to the inputs the results came from
    project.set_value("d_throat", 0.3e-3)                      # geometry: mesh, run and results outdated
    assert [project.status(s) for s in ("mesh", "run", "results")] == ["outdated"] * 3
    project.set_value("d_throat", 5.0)                         # invalid geometry input
    assert project.status("geometry") == "error"


def test_editing_an_input_file_marks_the_mesh_outdated(tmp_path):
    project = Project.create("nozzle_axi", tmp_path / "P.afsproj", values={"geometry_source": "Custom profile (CSV)"})
    build_project_mesh(project)
    assert project.status("mesh") == "ok"
    csv = project.folder / project.values["profile_csv"]
    csv.write_text(csv.read_text() + "\n", encoding="utf-8")    # any change of the content counts
    assert project.status("mesh") == "outdated"


def test_failure_is_red_until_the_inputs_change(tmp_path):
    project = Project.create("nozzle_axi", tmp_path / "P.afsproj")
    project.record_failure("mesh", "ValueError: something")
    assert project.status("mesh") == "error"
    project.set_value("nr", 41)
    assert project.status("mesh") == "none"


def test_open_reports_template_changes(tmp_path):
    project = Project.create("demo_heat1d", tmp_path / "P.afsproj")
    data = yaml.safe_load((project.folder / PROJECT_FILE).read_text())
    data["inputs"]["old_input"] = 1
    del data["inputs"]["k"]
    data["template_fingerprint"] = "abc"
    (project.folder / PROJECT_FILE).write_text(yaml.safe_dump(data))
    again = Project.open(project.folder)
    text = " ".join(again.warnings)
    assert "old_input" in text and "k" in text and "has changed" in text
    assert again.values["k"] == defaults(again.case.parameters())["k"]
    data["format_version"] = 99
    (project.folder / PROJECT_FILE).write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="newer"):
        Project.open(project.folder)


@pytest.mark.parametrize("template", ["demo_heat1d", "quasi1d_nozzle", "sod_shock_tube"])
def test_results_are_saved_and_read_back_exactly(tmp_path, template):
    case = load_case(template)
    changes = {"n_cells": 60} if template == "quasi1d_nozzle" else {}
    params = validate(case.parameters(), {**defaults(case.parameters()), **changes})
    out = run_case(case, params)
    payload = {"result": out.result, "reference": out.reference, "reference_lines": out.reference_lines,
               "checks": out.checks, "params": out.params, "run_s": 1.5}
    back = load_run(save_run(tmp_path, payload, out.mesh))
    a, b = out.result, back["result"]
    assert (a.iterations, a.converged, a.key_numbers, a.shape_note) == (b.iterations, b.converged, b.key_numbers,
                                                                         b.shape_note)
    assert np.array_equal(a.residuals, b.residuals)
    for key, f in a.fields.items():
        assert np.array_equal(f.values, b.fields[key].values) and (f.unit, f.label) == (b.fields[key].unit,
                                                                                         b.fields[key].label)
    if out.reference is not None:
        for key, f in out.reference.items():
            assert np.array_equal(f.values, back["reference"][key].values)
    if a.snapshots is not None:
        assert np.array_equal(a.snapshots.times, b.snapshots.times)
    if a.shape is not None:
        assert np.array_equal(a.shape.x, b.shape.x) and a.shape.marks == b.shape.marks
    assert [l.label for l in out.reference_lines] == [l.label for l in back["reference_lines"]]
    assert [c.as_dict() for c in out.checks] == [c.as_dict() for c in back["checks"]]
    assert np.array_equal(back["mesh1d"].x, out.mesh.x)


def test_command_line_runs_a_project_with_identical_results(tmp_path, capsys):
    project = Project.create("quasi1d_nozzle", tmp_path / "P.afsproj")
    assert main(["run", str(project.folder), "--set", "n_cells=60"]) == 0
    assert "Project:" in capsys.readouterr().out
    project = Project.open(project.folder)
    assert project.values["n_cells"] == 60 and project.status("results") == "ok"
    saved = project.load_results()["result"]
    case = load_case("quasi1d_nozzle")
    reference = run_case(case, validate(case.parameters(), {**defaults(case.parameters()), "n_cells": 60}))
    assert saved.key_numbers == reference.result.key_numbers
    for key, f in reference.result.fields.items():
        assert np.array_equal(saved.fields[key].values, f.values)
    assert (project.results_dir / "summary.yaml").is_file()
    assert main(["run", str(project.folder), "--out", str(tmp_path)]) == 1     # --out not for projects


def test_command_line_meshes_and_runs_a_2d_project(tmp_path, capsys):
    project = Project.create("nozzle_axi", tmp_path / "P.afsproj", {"mesh_preset": "Coarse", "max_iter": 20})
    assert main(["run", str(project.folder)]) == 2          # 2 = finished but not converged (20 iterations)
    assert "Results saved" in capsys.readouterr().out
    reopened = Project.open(project.folder)
    assert reopened.status("mesh") == "ok" and reopened.load_results()["result"].iterations == 20


def test_old_settings_file_becomes_a_project(tmp_path):
    old = tmp_path / "cases" / "nozzle_axi" / "settings" / "mine.yaml"
    old.parent.mkdir(parents=True)
    old.write_text(yaml.safe_dump({"case": "nozzle_axi", "parameters": {
        "d_exit": 0.0012, "geometry_source": "Custom profile (CSV)",
        "profile_csv": "cases/nozzle_axi/examples/n2_conical_nozzle.csv"}}))
    project = Project.from_old_settings(old, tmp_path / "Imported.afsproj")
    assert project.values["d_exit"] == 0.0012
    assert project.values["profile_csv"] == "geometry/n2_conical_nozzle.csv"
    assert project.params()["geometry_source"] == "Custom profile (CSV)"


def test_workspace_history_is_saved_and_part_of_the_fingerprints(tmp_path):
    from aeroflowsim.geometry_model import GeometryDocument
    from aeroflowsim.geometry_model.operations import Transform
    project = Project.create("external_2d", tmp_path / "P.afsproj")
    before = project.fingerprint("mesh")
    document = project.geometry_document()            # no history.json: the template's own geometry
    assert document.is_template_only() and project.edited_geometry is None
    document.add(Transform(kind="rotate", angle=5.0))
    project.set_geometry_document(document)
    assert project.dirty and not project.history_path.exists()     # written only by save()
    assert project.fingerprint("mesh") != before
    project.save()
    assert project.history_path.is_file()
    assert Project.open(project.folder).geometry_document() == document
    # Back to the unedited template geometry: the file goes and the old fingerprint returns.
    document.remove(document.operations[-1].id)
    project.set_geometry_document(document)
    assert project.fingerprint("mesh") == before
    project.save()
    assert not project.history_path.exists()
    project.set_geometry_document(GeometryDocument())   # an empty workspace is an edit, kept as a file
    project.save()
    assert project.history_path.is_file()
    copy = project.duplicate(tmp_path / "Q.afsproj")
    assert copy.geometry_document() == GeometryDocument()
