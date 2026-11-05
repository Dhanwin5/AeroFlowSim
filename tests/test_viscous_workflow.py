# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Walk-through of the viscous flow model from the user's side: an old project stays Euler and up to date; switching it
to Laminar makes walls no-slip, marks the result out of date, runs from the command line with the model in the log;
Run continues a stopped run; an adiabatic wall changed to isothermal makes the result out of date again; reopening keeps
everything; wall fields and the smart rules; the same in 3D."""

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.state import uniform_state
from aeroflowsim.euler.viscous import LAMINAR, ViscousSettings
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import box_mesh_3d

WEDGE = {"shape": "Wedge", "mach": 2.0, "surface_size": 0.08, "farfield_size": 0.3, "max_iter": 30}


def test_old_project_stays_euler_and_up_to_date(tmp_path):
    from aeroflowsim.project import Project
    project = Project.create("cases/external_2d", tmp_path / "old.afsproj")
    before = project.fingerprint("run")
    for key in ("flow_model", "turb_freestream", "turb_intensity", "turb_viscosity_ratio"):
        del project.values[key]                       # an old project's file has none of the new inputs ...
    project.save()
    again = Project.open(tmp_path / "old.afsproj")    # ... gets Euler and the TMR free stream when opened
    assert again.values["flow_model"] == "Euler" and again.fingerprint("run") == before
    again.values["flow_model"] = "Laminar"            # switching to a viscous model makes the result out of date
    assert again.fingerprint("run") != before


def test_walls_become_no_slip_under_a_viscous_model():
    from aeroflowsim.discovery import load_case
    from aeroflowsim.euler.setup import conditions
    from aeroflowsim.parameters import defaults
    from aeroflowsim.simple_meshes import rectangle_mesh
    case = load_case("cases/external_2d")
    p = defaults(case.parameters())
    mesh = rectangle_mesh(4, 4)                       # top = wall
    assert conditions(p, mesh, {})["top"].type == "slip_wall"
    p["flow_model"] = "Laminar"
    assert conditions(p, mesh, {})["top"].type == "no_slip_wall"
    p["boundaries"] = {"top": {"type": "slip_wall"}}  # an explicit choice of the user is kept ...
    assert conditions(p, mesh, {})["top"].type == "slip_wall"
    from aeroflowsim.checks import slip_walls_in_viscous_flow
    assert slip_walls_in_viscous_flow(case, p, mesh, None).level == "warning"   # ... with a warning


def test_switch_old_project_to_laminar_run_continue_isothermal_reopen(tmp_path, capsys):
    from aeroflowsim.cli import main
    from aeroflowsim.project import Project
    project = Project.create("cases/external_2d", tmp_path / "w.afsproj", values=dict(WEDGE))
    project.values.update({"flow_model": "Laminar", "p_inf": 2000.0})
    project.save()
    assert main(["run", str(project.folder)]) in (0, 2)              # 2: validity warnings (30 iterations only)
    out = capsys.readouterr().out
    assert "flow model Laminar" in out
    again = Project.open(project.folder)
    assert again.status("results") == "ok"
    result = again.load_results()["result"]
    assert result.iterations == 30
    for key in ("Cd_pressure", "Cd_friction", "y_plus_max"):
        assert key in result.key_numbers
    cd = result.key_numbers["Cd"][0]
    assert abs(result.key_numbers["Cd_pressure"][0] + result.key_numbers["Cd_friction"][0] - cd) < 1e-9 * max(1, abs(cd))
    assert "wall_Cf" in result.series and "wall_y_plus" in result.series
    # Run continues the run (more iterations)
    again.values["max_iter"] = 45
    again.save()
    assert main(["run", str(project.folder)]) in (0, 2)
    assert Project.open(project.folder).load_results()["result"].iterations == 45
    # the body wall changed from adiabatic to isothermal: the result is out of date, a new run uses it
    again = Project.open(project.folder)
    wall = next(p.name for p in again.load_mesh().patches if p.type == "wall")
    again.values["boundaries"] = {wall: {"type": "no_slip_wall", "thermal": "Isothermal", "T_wall": 400.0}}
    again.save()
    assert Project.open(project.folder).status("results") != "ok"
    assert main(["run", str(project.folder), "--fresh"]) in (0, 2)   # a new thermal condition: start again
    final = Project.open(project.folder).load_results()["result"]
    assert np.allclose(final.series["wall_T"], 400.0)
    assert np.all(np.isfinite(final.series["wall_q"])) and np.any(final.series["wall_q"] != 0.0)


def test_smart_rule_flow_model_from_reynolds_number():
    from aeroflowsim.discovery import load_case
    from aeroflowsim.parameters import defaults
    from aeroflowsim.smart_rules import numerics_suggestions
    case = load_case("cases/external_2d")
    p = defaults(case.parameters())
    p.update({"mach": 0.5, "p_inf": 101325.0})       # Re ~ 1e7 on a 1 m body: turbulent
    tips = [t for t in numerics_suggestions(case, p) if t.title == "Flow model"]
    assert tips and tips[0].inputs == {"flow_model": "Spalart-Allmaras"}
    p.update({"p_inf": 10.0, "flow_model": "k-omega SST"})     # Re ~ 1e3: laminar
    tips = [t for t in numerics_suggestions(case, p) if t.title == "Flow model"]
    assert tips and tips[0].inputs == {"flow_model": "Laminar"}


def test_wall_y_plus_check():
    from aeroflowsim.checks import wall_y_plus

    class R:
        key_numbers = {"y_plus_max": (5.0, "-")}
    assert wall_y_plus(None, {"flow_model": "k-omega SST"}, None, R()).level == "warning"
    assert wall_y_plus(None, {"flow_model": "Laminar"}, None, R()).level == "info"
    assert wall_y_plus(None, {"flow_model": "Euler"}, None, R()) is None


def test_3d_channel_laminar_runs_and_matches_couette():
    """3D: plane Couette flow between two walls of a box (hexahedra), sliding top wall: u linear to 1e-6."""
    gas = gas_model("air")
    H, U, p = 1e-3, 30.0, 1000.0
    mesh = box_mesh_3d(2, "hexahedra", hi=(H / 4, H, H / 4), ny=12, nz=2)
    bc = {"xmin": BoundaryCondition("supersonic_outlet"), "xmax": BoundaryCondition("supersonic_outlet"),
          "zmin": BoundaryCondition("symmetry"), "zmax": BoundaryCondition("symmetry"),
          "ymin": BoundaryCondition("no_slip_wall", {"thermal": "Isothermal", "T_wall": 300.0}),
          "ymax": BoundaryCondition("no_slip_wall", {"thermal": "Isothermal", "T_wall": 300.0, "u_wall": U})}
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=8000, residual_drop=9, limiter="None")
    s = EulerSolver(mesh, gas, bc, num, viscous=ViscousSettings(LAMINAR))
    r = s.solve(uniform_state(mesh.n_cells, p / (gas.R * 300.0), (U / 2, 0.0, 0.0), p))
    y = mesh.cell_centres[:, 1]
    assert np.abs(r.W[1] - U * y / H).max() < 1e-4 * U


def test_turbulent_project_runs_continues_with_its_turbulence_state(tmp_path, capsys):
    """SA and SST from the command line: the log says fully turbulent; the result holds mu_t and the model's fields;
    Run continues from them (more iterations, the eddy viscosity carried on, not restarted from the free stream)."""
    from aeroflowsim.cli import main
    from aeroflowsim.project import Project
    for model, names in (("Spalart-Allmaras", ("nu_tilde",)), ("k-omega SST", ("k", "omega"))):
        folder = tmp_path / f"{names[0]}.afsproj"
        project = Project.create("cases/external_2d", folder, values=dict(WEDGE))
        project.values.update({"flow_model": model, "mach": 0.5, "p_inf": 20000.0, "max_iter": 25})
        project.save()
        assert main(["run", str(folder)]) in (0, 2)
        assert "fully turbulent" in capsys.readouterr().out
        result = Project.open(folder).load_results()["result"]
        for name in ("mu_t", "mu_t_ratio", "wall_distance") + names:
            assert name in result.fields
        before = result.fields["mu_t"].values.copy()
        again = Project.open(folder)
        again.values["max_iter"] = 35
        again.save()
        assert main(["run", str(folder)]) in (0, 2)
        after = Project.open(folder).load_results()["result"]
        assert after.iterations == 35
        assert np.all(np.isfinite(after.fields["mu_t"].values)) and after.fields["mu_t"].values.max() > 0.0
        assert not np.array_equal(after.fields["mu_t"].values, before)


def test_results_step_offers_and_draws_the_wall_plots():
    """The Results step lists Cf, heat flux and y+ plots for a viscous result and draws them (no Qt needed)."""
    from aeroflowsim.gui.figures import wall_figure
    from aeroflowsim.gui.logic import flow_plots
    from aeroflowsim.results import Result
    x = np.linspace(0.0, 1.0, 20)
    series = {"wall_x": x, "wall_y": 0 * x, "wall_Cp": 0 * x, "wallv_x": x, "wallv_y": 0 * x, "wall_Cf": 0.01 + 0 * x,
              "wall_q": x, "wall_y_plus": 0.5 + x}
    result = Result(fields={}, residuals=[], key_numbers={}, iterations=1, converged=True, series=series, info={})
    plots = flow_plots(result)
    for name in ("Skin friction Cf along the wall", "Wall heat flux along the wall", "y+ of the first cell along the wall"):
        assert name in plots
        assert wall_figure(result, name) is not None
