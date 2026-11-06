# AeroFlowSim tools: reference

## The tools

| Tool | What it does |
|---|---|
| `list_templates` | Installed templates (cases): name, title, what it solves |
| `describe_template(template)` | Every input: key, unit, min / max, default, options, `only_if`, help; known limits |
| `list_gases`, `describe_gas(gas)` | Built-in gas library, properties at 300 K with sources |
| `list_shapes` | Shape library (bodies, nozzles, intakes) with each shape's inputs |
| `create_project(template, name)` | New project in the workspace (refused if the name exists) |
| `list_projects` | Projects in the workspace with their step status |
| `get_inputs(project)` | Inputs in use now, with units; step statuses |
| `set_inputs(project, inputs)` | Change inputs (`{key: {value, unit}}`); returns applied / unchanged / rejected / hints |
| `set_geometry(project, shape, params)` | Choose a library shape and its inputs |
| `import_geometry(project, path, input?, enclosure?, axisymmetric?)` | Bring a file from the workspace into the project |
| `mesh(project, preset?)` | Build the mesh; cell count, cell types, patches, mesh checks |
| `check(project)` | Problems, mesh and setup checks, smart-rule hints, run estimate, ready yes/no |
| `run(project, confirm?, fresh?)` | Start a run in the background; may answer `needs_confirmation` |
| `continue_run(project, confirm?)` | Carry on from the saved result |
| `job_status(job_id)` | Status, iteration, residual drop, monitors, elapsed, ETA |
| `stop_job(job_id)` | Clean stop after the current iteration (the flow is saved) |
| `get_results(project)` | Verdict, key numbers, failed checks, what to try, known limits |
| `get_plot(project, kind, field?)` | PNG: residuals, fields (1D), contour (2D/3D), mesh, wall |
| `compare_runs(projects)` | Verdicts and key numbers side by side |
| `export(project, format)` | csv, vtu, tecplot, or the mesh as su2 / msh / cgns |
| `make_report(project, pdf?)` | Automatic HTML (PDF) report |
| `list_validation_cases`, `get_validation_report(case?)` | Measured errors against theory and experiment |
| `search_docs(query)` | User guide, theory manual, gap register sections |

Every answer has `ok`; on `ok: false` read `error`, tell the user in plain words, and fix the cause (do not retry
the same call unchanged).

## Reading checks

Each check has `level` info / warning / error and a message that already says what to do. Typical ones:

* **Convergence** (residual drop in orders of magnitude; 6 expected for steady cases) and **Monitors settled**
  (thrust, Cd, mass flow stopped changing): both needed before a steady number is an answer.
* **Mass balance**, **Thrust two ways** (exit plane vs wall integration), **Total-pressure loss** in a shock-free
  nozzle: consistency of the solution.
* **Mesh** checks (negative volume = error and the run is refused; aspect ratio, non-orthogonality, skewness, first
  layer, smallest cell) and **Run memory** (3D).
* **Gas** checks: ideal-gas validity (Peng-Robinson Z), condensation risk, temperature range of the gas data.
* **Wall y+** (viscous): first-cell y+ above about 2 means the wall shear and heat flux are not resolved.
* **Run status**: diverged (do not use the fields), stopped, or ended normally.

`what_to_try` (after a divergence or CFL reductions) lists changes with reasons: lower CFL, a first-order start, a
better initial solution. Offer them; apply with `set_inputs` after the user agrees, then `run` (fresh if the
diverged state should be discarded).

## Example: a sweep, asked properly

User: "Thrust of my nozzle at back pressures 0.1, 0.5 and 1 bar."
1. One project per back pressure (`nozzle 0.1 bar`, ...), or one project re-run three times (each run replaces the
   project's own results, so record the numbers between runs).
2. `check` the first; if the estimate needs confirmation, ask once for the whole sweep: "3 runs, about 4 min each."
3. Report a small table: back pressure, thrust, verdict.

## Example: an imported mesh

User put `wing.su2` in the workspace folder. `create_project("imported_mesh", "wing")`,
`import_geometry("wing", "wing.su2")`, read `problems` (boundary names mapped to types), `mesh`, `check`, `run`.

## Example: the request needs confirmation

`run` -> `{"status": "needs_confirmation", "estimate": {"minutes_at_most": 42, "memory_GB": 3.1}}` -> tell the user
"This run may take up to about 42 minutes and 3 GB of memory. Start it?" and wait.
