# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Automatic report (aeroflowsim/post/report.py): every section, self-contained HTML without web addresses, a PDF,
the command line, and run + report with Qt and VTK made unimportable."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from aeroflowsim.cli import main
from aeroflowsim.post.report import SECTIONS, build, write_report
from aeroflowsim.project import Project, run_project

PROJECT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module", params=["nozzle_axi", "external_2d", "sod_shock_tube"])
def solved(request, tmp_path_factory):
    values = {"nozzle_axi": {"mesh_preset": "Custom", "nx": 30, "nr": 6},
              "external_2d": {"shape": "Wedge", "half_domain": True, "domain_shape": "Rectangle", "upstream": 0.5,
                              "downstream": 0.5, "height": 1.0, "surface_size": 0.06, "farfield_size": 0.15,
                              "max_iter": 1500},
              "sod_shock_tube": {}}[request.param]
    project = Project.create(request.param, tmp_path_factory.mktemp(request.param) / "p.afsproj", values)
    run_project(project)
    return project


def test_report_has_every_section_and_no_web_addresses(solved):
    doc = build(solved)
    assert [t for t, _ in doc.sections] == list(SECTIONS)
    paths = write_report(solved)
    html = paths[0].read_text(encoding="utf-8")
    assert not re.search(r"(https?:|www\.|ftp:)", html)          # privacy rule 12: nothing to fetch
    for title in SECTIONS:
        assert title in html
    assert paths[1].read_bytes()[:4] == b"%PDF" and paths[1].stat().st_size > 10_000
    if solved.case.name != "sod_shock_tube":
        assert html.count("data:image/png;base64") >= 4


def test_report_from_the_command_line(solved, tmp_path, capsys):
    assert main(["report", str(solved.folder), "--out", str(tmp_path), "--format", "html"]) == 0
    assert list(tmp_path.glob("*.html"))
    assert main(["report", str(tmp_path / "missing.afsproj")]) == 1


def test_run_and_report_work_without_qt(tmp_path):
    folder = tmp_path / "s.afsproj"
    code = ("import sys\n"
            "for name in ('PySide6', 'pyvista', 'pyvistaqt', 'vtk', 'vtkmodules'):\n"
            "    sys.modules[name] = None\n"
            "from aeroflowsim.cli import main\n"
            "from aeroflowsim.project import Project\n"
            f"Project.create('sod_shock_tube', r'{folder}')\n"
            f"assert main(['run', r'{folder}']) in (0, 2)\n"
            f"assert main(['report', r'{folder}']) == 0\n"
            "import aeroflowsim.post, aeroflowsim.post.export, aeroflowsim.post.xy, aeroflowsim.post.pictures\n"
            "print('ok')\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PROJECT_DIR)
    assert out.stdout.strip().endswith("ok"), out.stderr[-2000:]
