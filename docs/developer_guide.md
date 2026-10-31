# AeroFlowSim developer guide: the desktop GUI

This guide explains how the desktop GUI is built, for anyone who wants to change or extend it.
It assumes Python, not Qt. Physics and numerics are in `docs/theory_manual.md`.

## 1. The big picture

```
                 ┌──────────────────────── aeroflowsim/gui/  (the ONLY place with Qt / VTK) ───────────────┐
 python -m       │  app.py ── MainWindow (main_window.py)                                                  │
 aeroflowsim gui │            ├─ pages: steps/geometry.py, mesh.py, setup.py, run.py, results.py, welcome  │
                 │            ├─ InputPanel (panel.py)  ◀── PanelModel (panel_model.py, no Qt)             │
                 │            ├─ WorkflowStrip (workflow_strip.py)                                         │
                 │            ├─ MeshView (vtk_view.py), PlotCanvas (figures.py)                           │
                 │            └─ JobRunner (jobs.py) ── QTimer polls ──┐                                   │
                 └──────────────────────────────────────────────────────│───────────────────────────────────┘
                                                                        ▼
   no GUI code:  project.py (Project, fingerprints)   tasks.py (Worker: warm helper process)
                 result_io.py (run.npz)               engine.run_case  ◀── also used by cli.py and scripts
                 geometry_preview.py                  cases/<template>/schema.toml + case.py
```

Rules that keep this healthy (all tested):

- Only `aeroflowsim/gui/` (and the old `app.py`) may import PySide6, PyVista, VTK or streamlit
  (`tests/test_no_gui_in_solver.py`). The command line works with Qt not installed.
- The GUI has no network code and opens only local files (`tests/test_gui_privacy.py`).
- Decisions are kept out of widgets where possible (`panel_model.py`, `gui/logic.py`,
  `project.py`), so they are unit-tested without a window.

## 2. Qt in five ideas

1. **QApplication and the event loop.** `app.py` creates one `QApplication`, shows the window
   and calls `app.exec()`. From then on Qt waits for events (clicks, keys, timers) and calls
   your functions. Never block in a function called by Qt: long work goes to the background worker.
2. **Widgets** are the visible pieces (`QPushButton`, `QComboBox`, `QDockWidget`, ...). They sit in
   layouts (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`) that size them automatically.
3. **Signals and slots.** A widget *emits a signal* when something happens; any function
   *connected* to it (a slot) is then called:
   ```python
   button.clicked.connect(window.generate_mesh)       # click -> generate_mesh()
   panel.value_changed.connect(window.on_panel_edit)   # our own signal: (name, value)
   ```
   Prefer connecting methods over lambdas for long-lived connections: Qt disconnects a method by
   itself when its object is deleted (a lambda can call a deleted window, which we hit in testing).
4. **QMainWindow** gives the menu bar, toolbars, a central widget and dockable panels
   (`QDockWidget`). Each dock has an `objectName`, so `saveState()`/`restoreState()` remember the
   layout between sessions (stored with the theme and recent projects in an INI file via `QSettings`).
5. **Actions** (`QAction`) are commands with a text, shortcut and tooltip, shared by menus and
   toolbars (`MainWindow.build_actions`).

## 3. The main window and the workflow

`MainWindow` owns the state: `project` (a `Project`), `mesh`, `mesh_checks`, `results` (the run
payload), the `JobRunner` and the undo stack. Pages only display this state and call window
methods (`generate_mesh`, `run_case`, `cancel_job`, `reset_inputs`, `show_properties`, `log`).

- **Pages** (`gui/steps/`): one per workflow step. Each has `refresh()`, called after anything changed.
- **Workflow strip** (`workflow_strip.py`): a chip per step coloured by `Project.status(step)`;
  clicking a chip calls `MainWindow.go_to(step)`. A running job shows its progress and a ✕ (Cancel)
  inside its own chip. It replaces a status bar and a step tree.
- **Docks:** Inputs (the panel of the current step), Properties (clicked cell/boundary), Messages
  (log), Validity checks.

### Adding a step page

1. Write `gui/steps/<name>.py` with a `QWidget` subclass taking `window`, with `refresh()`.
2. Add it to `MainWindow.pages` and to `WORKFLOW` in `project.py` (with its status rule in
   `Project.status`) and `TITLES`/`SHORTCUTS` in `workflow_strip.py`.

## 4. The input panel (zero GUI code per template)

`PanelModel(param_list, step)` turns every `Parameter` of a template into a `WidgetSpec` (kind,
label with unit, tooltip with range, options and which need a missing package, file filter) and
answers `visible(values)` (show_if, nested) and `problems(values)` (the usual value checks).
`InputPanel` draws the specs: number boxes keep exactly what was typed (no silent clamping; the
red message explains), arrow keys/wheel step a value, groups collapse, "?" shows the help.

Each input has a `step` in `schema.toml` (`geometry`, `mesh` or `setup`, default `setup`); the window
makes one panel per step. Changing a value: panel emits `value_changed` → `MainWindow.on_panel_edit`
pushes a `SetInputs` undo command → its `redo()` calls `apply_values`, which updates the project,
every panel, the statuses, and schedules the geometry redraw / automatic re-mesh.

### Units

The window keeps the user's display units (`MainWindow.units`, a `UnitPreferences` of
`aeroflowsim/units.py`, saved in QSettings, chosen in View > Units). `PanelModel(param_list, step,
units)` gives every float input whose SI unit has a quantity (m, Pa, K, kg/s, N, m², m/s) a display
unit: label, range and problem messages are in that unit, `text_to_value` turns typed text into SI and
`display_text` turns SI into text. The panel keeps the exact SI value of an unchanged box, so pressing
Enter or switching units never counts as an edit. Result pages convert only for display
(`logic.readable(..., prefs=...)`, `logic.display_field`, `field_figure(..., prefs)`, the CSV export);
project files, `run.npz`, the command line and the validation report stay SI. Changing units rebuilds
the panels (`MainWindow.set_units`).

Check messages: a check puts its dimensional numbers into the message as `Quantity` objects
(`aeroflowsim/units.py`) with placeholders `{0}`, `{1}` in the text. `CheckResult.message` is the SI text
(command line, `summary.yaml`); `CheckResult.text(prefs)` is what the Validity checks panel shows. The
Geometry Dimensions table and Properties use `geometry_logic.Shown(prefs)` (lengths, areas, volumes in
the length unit cubed); the mesh table and cell Properties use `readable(..., prefs=...)`.

### Gas inputs

An input of type `gas` is drawn as a dropdown (`gui/gas_logic.gas_choices`: built-in gases, the
project's custom gas, "My gases" from the user's library, "New custom gas..."), with a "Custom..." button
for a variant of the chosen gas. The panel asks its `GasHandler` (`MainWindow`'s `ProjectGases`) to copy
a library gas into `<project>/gases/` and to run the custom-gas form (`gui/gas_dialog.py`; checks in
`gas_logic.form_to_toml`). The Details area shows `gas_detail_rows`: every value with its source.
Tools > Gas library shows all gases and makes custom ones without a project.

### Boundary-condition table

An input of type `boundaries` (added to every template with `euler_solver = true`, see
`aeroflowsim/euler/setup.py`, `solver_parameters`) is drawn by `BoundaryTable` in `panel.py`: one framed row per
named boundary (patch) of the current mesh, with a type dropdown, a Default button and the inputs of the
chosen type (`BC_TYPES` in `aeroflowsim/euler/boundary.py`, each input a `Parameter`, so units, ranges and
show_if work as everywhere). The rows are decided without Qt in `gui/boundary_logic.py` (`rows`,
`with_type`, `with_value`, `without`, unit-tested). The panel gets them from its `BoundaryHandler`
(`MainWindow`'s `ProjectBoundaries`), which knows the mesh and the template's `boundary_defaults(params)`.
The stored value holds only the boundaries the user changed; the others follow the defaults, which follow
inputs such as p0 or the free stream (`panel.refresh_boundaries()` after every input change and new mesh).
Every edit is one undoable input change.

## 5. The VTK view

`MeshView` (`vtk_view.py`) holds a `pyvistaqt.QtInteractor`: a VTK render window inside a Qt widget.

- `mesh_to_grid(mesh)` re-packs our face-based `Mesh` (already VTK cell types and node order)
  into a `pv.UnstructuredGrid`; `patch_lines(mesh)` makes the boundary faces lines with patch data.
- 2D view: parallel projection, "2D style" (left drag pans, wheel zooms), `fit()` fits width *and*
  height, `zoom_to_body()` for bodies in a large far field.
- Picking: a click is a press + release without moving. Cells: the cell *containing* the clicked
  point (exact; VTK's cell picker uses a tolerance and returned neighbours on small cells). Boundary
  edges: the edge with the smallest exact distance, within 8 pixels.
- The view needs OpenGL; Qt's "offscreen" platform has none, so GUI tests use a real (or virtual,
  Xvfb) display - see `tests/gui/conftest.py` and the CI workflow.

2D results (Results step): the same `MeshView` shows a field per cell (`show_mesh(mesh, values, title,
cmap=..., clim=..., keep_camera=True)`), with room under the drawing for the horizontal colour bar; a click
shows every field of that cell in Properties (`logic.cell_value_rows`). Under it, `figures.wall_figure`
(wall p/p0 against quasi-1D theory, or Cp) and the convergence history.

1D results and plots use matplotlib: `PlotCanvas` (`figures.py`) embeds a `Figure` with its standard
toolbar (zoom, pan, save). `visualise.py` figures (contour, shape view, x-t diagram) are reused unchanged.

## 6. Background jobs

`aeroflowsim/tasks.py` (no GUI code):

- `Worker` starts **one helper process** (`multiprocessing`, "spawn") and keeps it warm, because
  starting Python with numpy/scipy costs ~1.4 s on Windows while a small mesh takes 0.04 s.
- `Worker.submit(Job("mesh" | "run", case_folder, params, out_dir, mesh))` sends a job; the helper
  loads the template itself and calls the same functions as the command line (`case.build_mesh`,
  `engine.run_case`), so GUI, command line and scripts give identical results (tested).
- Messages come back through a queue: stage text, residual batches (every 0.1 s), done/stopped/error.
  A 2D solver calls `progress(iteration, residual, info)`; the batches then also carry the residual of every
  equation, the monitors (thrust, mass flow, Cd, Cl, Cm) and the positivity count, which the Run page plots
  live (`figures.residual_figure`, one small plot per monitor unit). `Job.restart` names the
  `results/run.npz` to carry on from: Run continues the current solution on the same mesh by default
  (`MainWindow.continuation`, `Project.continuation`, mesh fingerprint in `Result.info`), with the iteration
  numbers, residual normalisation, histories and frozen limiter carried on (`euler/solver.py`, `Continuation`);
  *Start from scratch* (`run_from_scratch`) sends no restart.
- **Stop** of a run: a shared flag is seen by the progress callback between two iterations. A 2D run
  (its solver passes `info`) gets `True` back, ends after that iteration and finishes normally with the
  flow of that moment (status "stopped", restartable); the helper then reports the stage "Stopped: saving
  the results ..." and is never terminated while it saves. A 1D run raises `StopRequested` (no results). **Cancel** of a mesh (Gmsh cannot be interrupted) or a run that does not stop
  within 3 s: the helper process is terminated and a new one started.
- `__main__.py` must keep its `if __name__ == "__main__":` guard: "spawn" imports it again in the helper.

`gui/jobs.py` (`JobRunner`) polls the worker with a `QTimer` and emits `started/updated/ended`.
The window takes the project fingerprint when a job is *sent* (the user may keep editing).

## 7. The project file

```
My Nozzle.afsproj/
    project.yaml   format_version, aeroflowsim_version, template, template_fingerprint,
                   created, modified, inputs {name: value}, steps {mesh: {...}, run: {...}}
    geometry/      copied input files (relative paths in inputs)
    mesh/          mesh.npz (exact), mesh.vtu (ParaView), mesh1d.npz (1D templates)
    results/       run.npz (exact results, reopened by the GUI) + fields.csv, residuals.csv,
                   summary.yaml, PNG plots (as the command line writes them)
```

**Status by fingerprints.** A fingerprint is a SHA-256 of everything a product depends on: the
inputs of the relevant steps (geometry → mesh → run), the contents of input files, the template's
`schema.toml` and `case.py` and the AeroFlowSim version. `Project.status(step)` compares the stored
fingerprint of the mesh or run with the current one: ok (green), outdated (amber), none (grey),
error (red, until the inputs change), disabled (mesh-only templates). Undoing a change brings the
old fingerprint back, so the status turns green again without recomputing.

Making a mesh or a run saves the project (the files on disk always match `project.yaml`).

## 8. The geometry workspace

The Geometry step of 2D templates (those whose `case.py` has `workspace_settings`) is a small CAD
program. Its parts, from the bottom up:

| Layer | Module | Qt? |
|---|---|---|
| History, operations, replay | `geometry_model/document.py`, `operations.py` | no |
| CAD kernel (only place calling `gmsh.model.occ`), stable edge ids | `geometry_model/kernel.py` | no |
| Replayed geometry as plain data (vertices, edges, faces, names, regions) | `geometry_model/built.py` | no |
| Import, healing, export; picking; snapping; boundary types and suggestions | `geometry_model/*.py` | no |
| Page logic: fields of each operation, prefilled operations, boundary table, handles | `gui/geometry_logic.py` | no |
| Drawing, picking clicks, drag modes | `gui/geometry_view.py` | yes |
| Forms and dialogs (generated from `FIELDS`) | `gui/geometry_forms.py` | yes |
| The page (tool bar, History / Boundaries / Dimensions tabs, sketch bar) | `gui/steps/geometry.py` | yes |
| Mesher for edited geometry | `workspace_mesh.py` | no |

**Data flow.** The project holds the history in memory (`Project.edited_geometry`, written to
`geometry/history.json` by Save; `None` = not edited, the template's own geometry). The page replays
it (`replay(document, project.replay_context())`) only when the history or the geometry inputs
changed, draws the result and keeps the selection as `(kind, id)` pairs. Every edit builds a NEW
document and calls `window.edit_geometry(document, text)`, which pushes one `SetGeometry` undo
command (old and new history); undo/redo call `window.apply_geometry`.

**Adding an operation.** One class in `geometry_model/operations.py` (`type`, `title`, `DEFAULTS`,
`apply(kernel, context)`), listed in `OPERATIONS`; one `FIELDS` entry in `gui/geometry_logic.py` for
its settings form; a branch in `operation_for()` if it is pre-filled from the selection; a tool bar
entry in `TOOLS`. Name new curves with `kernel.name_edge` (or let `kernel.relabel` match them after a
boolean).

**Templates.** A template joins the workspace with `workspace_settings(params, built)` (its Gmsh
settings) and, for the suggested sizes, `size_inputs(params, built)`. Its own geometry is the
`TemplateShape` operation (and `TemplateEnclosure` for a far field), whose parameters are the
template's geometry inputs. `workspace_mesh.mesh_for()` uses the template's own `build_mesh` while
the history is unedited, so validated meshes never change by accident.

**Meshing jobs.** `Job.geometry` carries the edited history (a dict) to the helper process;
`tasks._mesh_job` calls `mesh_for(case, params, document, folder)` like the command line.

## 9. Tests

- `tests/test_panel_model.py`, `tests/test_gui_logic.py`, `tests/test_project.py`,
  `tests/test_tasks.py`, `tests/test_geometry_*.py`, `tests/test_workspace_mesh.py`: no window.
- `tests/gui/` (pytest-qt): the panel, the job runner and the main window driven like a user
  (mesh, click a cell, automatic re-mesh, undo/redo, run and reopen, cancel, theme; geometry
  workspace: click, name, undo, sketch, every tool, import -> name -> refine -> mesh).
  Preferences go to a temporary INI file, never the user's own.

Run them all: `.venv\Scripts\python.exe -m pytest` (test windows appear briefly on Windows).

## Solver speed: Numba kernels and threads (Speed stage (Numba))

- `aeroflowsim/compute.py` holds two settings: backend (`auto` / `numba` / `numpy`; env `AEROFLOWSIM_BACKEND`) and
  threads (`None` = physical cores - 1, at most 16; env `AEROFLOWSIM_THREADS`). The CLI sets them with `--backend`
  and `--threads`; the GUI stores the thread count under `solver/threads` (Tools > Preferences,
  `gui/preferences_dialog.py`) and sends it with every run `Job` (`tasks.py`), so the helper process uses it from the
  next run on. It is a computer setting, not a project input: it never changes a fingerprint.
- `EulerSolver._choose_backend()` imports `euler/kernels.py` (and so Numba) only when the first solver is built;
  `_residual_numba()` is the kernel version of `residual()`. Missing Numba or a gas model without kernels: the NumPy
  path runs and `solver.backend_note` says why (shown by the command line, stored in the run info).
- Run info records `backend`, `threads`, `backend_note` (Run banner, report, `print_report`).
- **Kernel rules (GPU-ready):** a kernel is a pure function of flat arrays and numbers; outputs are passed in
  (allocated once in `KernelData`); no allocation, Python objects or global state inside loops; each `prange`
  iteration writes only its own cell or face (face sums by gather), so results never depend on the thread count.
- Compilation: `cache=True`, compiled at first use (about 20-40 s once per machine), then loaded from
  `__pycache__`. If no cache folder is writable, `kernels.CACHE` is False and the kernels compile in memory at each
  start. The installer collects `numba` and `llvmlite` (`tools/build_installer.py`).
- Timing: `python tools/timing.py` (table), `--profile`, `--threads-table`; results in `validation/timing.md`.

## Post-processing (`aeroflowsim/post/`, post-processing and alpha release stage)

All post-processing logic lives in `aeroflowsim/post/` and imports neither Qt nor VTK, so the command line
(`report`, `export`, `snapshot`), scripts, the automatic report and the GUI share it. The GUI only draws.

| Module | Role |
|---|---|
| `solution.py` | `Solution`: mesh + cell fields + gas + boundary conditions of one result; geometry, gradients, boundary face values and the solver's stored boundary fluxes, all computed once (cached) |
| `fields.py` | derived fields (`_DERIVED` table + `_compute`), custom formulas (ast whitelist, unit algebra), node values |
| `sampling.py` | point location, linear reconstruction, line cutting (one piece per cell), interpolation onto another mesh |
| `surfaces.py` | `Surface` (stored definition) -> `SurfaceData` (segments on the current mesh) |
| `integrals.py` | surface / volume operations, flux balance, forces and moments |
| `definitions.py` | report definitions, `MonitorEvaluator` (during the run), `ReportFileWriter` (CSV) |
| `xy.py`, `pictures.py` | matplotlib figures (paper style) |
| `snapshots.py`, `compare.py`, `export.py`, `report.py` | snapshots, differences, files, HTML / PDF report |
| `animation.py` | flow animation: `FrameRecorder` (used by the solver), `Animation`, `results/animation.npz`, `Playback` (play / step / loop logic), GIF / MP4 export |

GUI side: `gui/results_logic.py` (Scene and the arrays to draw, no Qt), `gui/flow_view.py` (VTK drawing, linked
views), `gui/post_panels.py` (the six panels), `gui/steps/results.py` (the page that owns the Solution).
Project settings are stored in `project.yaml` under `surfaces`, `report_definitions`, `custom_fields`, `scenes`,
`xy_plots`, `init_patches`, `interpolate_new_mesh` (`Project.post`, `Project.set_post`). A run receives them
through `run_case(..., extras=project.run_extras(mesh))`; `aeroflowsim/euler/setup.py` reads them from the context
variable `RUN_EXTRAS` (monitors, patches, interpolation).

**Flow animation:** `EulerSolver.solve(..., recorder=)` hands a `post.animation.FrameRecorder` the initial state,
every accepted state it asks for (`due(it)`; the state is already computed, so recording costs only a float32 copy)
and the final state; a CFL back-off calls `rewind(good_it)`. `euler/setup.solve` builds the recorder from
`extras["animation"]` (the project's `post["animation"]` = `{"record", "every"}`; no extras = no recording, so scripts
and the validation suite are unchanged) and the earlier frames of a continued run (`Continuation.animation`, loaded by
`result_io.continuation_data`). The frames travel as `Result.animation`; `result_io.save_run` writes
`results/animation.npz` or removes a stale one, so the frames share the run's fingerprint (out of date together). The
settings are post-processing settings, not template inputs, so changing them never marks results out of date. GUI:
`gui/animation_panel.py` (`PlaybackBar` with a QTimer driving `Playback`; `AnimationPanel`); `ResultsPage.view_solution`
returns the frame's Solution while the Animation tab is open, and `draw_view` swaps in the range over all frames.

**How to add a derived field:** add a line to `_DERIVED` in `post/fields.py` (label, unit, group) and its formula
in `_compute`; add a test with a field whose value is known (e.g. a linear or solid-body field). It then appears in
every field list, the report, the exports and the formulas.

**How to add a surface type:** add it to `TYPES` / `TYPE_LABELS` in `post/surfaces.py`, store its parameters in
`Surface` (`to_dict` / `from_dict`), build its segments in `evaluate_surface`, and add its inputs to
`SurfaceDialog` in `gui/post_panels.py`. Integrals, XY plots and report definitions then work on it unchanged.

**How to add a report section:** in `post/report.py` add the title to `SECTIONS` and a block in `build()` using
`d.section`, `d.text`, `d.table`, `d.figure`; `tests/test_report.py` checks that every section is present.

**Validation sets:** a `validate.py` calls `validation.common.is_quick()` to choose its coarse meshes for the quick
set (CI on every push, under 10 minutes); a reference may have `tolerance_percent_quick`. `run_all.py --quick` writes
`report_quick.md`; the full set writes `report.md`.
