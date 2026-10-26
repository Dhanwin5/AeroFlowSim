# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The run engine: ONE function that runs a case, used by the GUI, the command line and scripts.

    import aeroflowsim
    out = aeroflowsim.run_case("cases/quasi1d_nozzle", {"p_back": 2.5e5})
    print(out.result.key_numbers["M_exit"], [c.message for c in out.checks])

Because the GUI (through aeroflowsim/job.py) and the command line (aeroflowsim/cli.py) both call
this same function, the same case with the same inputs gives identical numbers in both.

Steps: load case -> check inputs -> mesh -> mesh checks -> setup checks -> solve -> reference ->
validity checks -> (save files). If a mesh check reports an error (e.g. a cell with negative volume),
the solver is not started and MeshError is raised; a setup-check error (e.g. an angle of attack on an
axisymmetric mesh) raises SetupError. A case without a solver yet (solver = false in its
schema.toml) raises ValueError with the case's message.
"""

from dataclasses import dataclass, field
from pathlib import Path

from aeroflowsim.case import get_reference, get_reference_lines
from aeroflowsim.checks import CheckResult, run_checks, run_mesh_checks, run_setup_checks
from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.results import Result
from aeroflowsim.runner import save_outputs


class MeshError(ValueError):
    """The mesh failed a mesh check at "error" level, so the solver was not started."""


class SetupError(ValueError):
    """The inputs failed a setup check at "error" level (e.g. an angle of attack on an axisymmetric
    mesh), so the solver was not started."""


@dataclass
class RunOutput:
    """Everything one run produces."""

    case: object                 # the Case that was run
    params: dict                 # the checked input values used {key: value}
    mesh: object                 # the mesh used
    result: Result               # what case.run() returned
    reference: dict | None = None                         # exact / theory fields (or None)
    reference_lines: list = field(default_factory=list)   # exact lines for the x-t diagram
    checks: list[CheckResult] = field(default_factory=list)   # validity check results
    out_dir: Path | None = None  # folder the files were saved to (None = not saved)


def _report_values(case, values, mesh, result, extras):
    """{name: [value, unit]} of the project's report definitions on the final result (NaN + reason if one fails)."""
    from aeroflowsim.post.definitions import definitions_from, evaluate_definitions
    from aeroflowsim.post.solution import Solution
    from aeroflowsim.post.surfaces import surfaces_from
    try:
        sol = Solution.from_result(mesh, result, values, case=case,
                                   custom_fields=extras.get("custom_fields") or {})
    except ValueError:
        return {}
    out = evaluate_definitions(sol, definitions_from(extras["report_definitions"]), surfaces_from(extras.get("surfaces")))
    return {k: [float(v), u] for k, (v, u) in out.items()}


def _no_progress(iteration, residual, info=None):
    """Default progress callback: do nothing."""


def run_case(case, params=None, *, mesh=None, progress=None, out_dir=None, restart=None, extras=None) -> RunOutput:
    """Run one case and return a RunOutput.

    case      a case folder ("cases/quasi1d_nozzle"), a case name ("quasi1d_nozzle"),
              or an already loaded Case
    params    {key: value} inputs to change; the others keep their default from schema.toml
    mesh      a ready mesh (the GUI passes the one shown in its Mesh tab); None = build it here
    progress  function progress(iteration, residual[, info]) called by the solver every iteration; a 2D
              solver ends cleanly (status "stopped") when it returns True
    out_dir   folder to save fields.csv, summary.yaml, plots ... into; None = save nothing
    restart   fields {key: array} of a previous result on the same mesh, for cases that can continue a
              run (case.run(..., restart=...)); None = start from the case's own initial solution
    extras    project post-processing settings of 2D runs (not template inputs): {"report_definitions",
              "surfaces", "init_patches", "interpolate"} (see aeroflowsim/euler/setup.py, RUN_EXTRAS). Report
              definitions are evaluated after the run (result.info["report_values"]); those marked "monitor"
              are evaluated every iteration and written to <out_dir>/report_<name>.csv while the run goes on.
    """
    if isinstance(case, (str, Path)):
        case = load_case(case)
    values = dict(params or {})
    if hasattr(case, "parameters"):          # fill in defaults, then check every value
        param_list = case.parameters()
        values = validate(param_list, {**defaults(param_list), **values})
    if not getattr(case, "has_solver", True):
        raise ValueError(case.solver_message)
    if mesh is None:
        mesh = case.build_mesh(values)
    mesh_errors = [c for c in run_mesh_checks(case, values, mesh) if c.level == "error"]
    if mesh_errors:   # e.g. inverted cells: the solver must not run on this mesh
        raise MeshError(" ".join(f"{c.name}: {c.message}" for c in mesh_errors))
    setup_errors = [c for c in run_setup_checks(case, values, mesh) if c.level == "error"]
    if setup_errors:  # e.g. an angle of attack on an axisymmetric mesh: the run would not mean anything
        raise SetupError(" ".join(f"{c.name}: {c.message}" for c in setup_errors))

    extras = dict(extras or {})
    writer = None
    monitor_defs = [d for d in extras.get("report_definitions") or [] if d.get("monitor")]
    if out_dir is not None and monitor_defs:
        from aeroflowsim.post.definitions import ReportFileWriter
        writer = ReportFileWriter(out_dir, [d["name"] for d in monitor_defs], restart)
    user_progress = progress or _no_progress

    def tracked(iteration, residual, info=None):
        if writer is not None and info is not None:
            writer.add(iteration, info.get("monitors", {}))
        return user_progress(iteration, residual, info) if info is not None else user_progress(iteration, residual)

    token = None
    if extras:
        from aeroflowsim.euler.setup import RUN_EXTRAS
        token = RUN_EXTRAS.set(extras)
    try:
        run_progress = tracked if writer is not None else (progress or _no_progress)
        if restart is not None:
            result = case.run(values, mesh, run_progress, restart=restart)
        else:
            result = case.run(values, mesh, run_progress)
    finally:
        if token is not None:
            from aeroflowsim.euler.setup import RUN_EXTRAS
            RUN_EXTRAS.reset(token)
        if writer is not None:
            writer.close()
    if extras.get("report_definitions") and getattr(result, "info", None) is not None and "rho" in result.fields:
        result.info["report_values"] = _report_values(case, values, mesh, result, extras)
    output = RunOutput(case=case, params=values, mesh=mesh, result=result,
                       reference=get_reference(case, values, mesh),
                       reference_lines=get_reference_lines(case, values, mesh),
                       checks=run_checks(case, values, mesh, result))
    if out_dir is not None:
        output.out_dir = save_outputs(out_dir, output)
    return output
