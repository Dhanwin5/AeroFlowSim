# Post-processing and alpha release - Post-processing at Fluent level (and beyond), trust (MMS + validation suite), report, installer, 2D alpha release

**Model: Opus** (one large session with many design decisions and verification numerics).

Paste everything below the line into a NEW Claude Code session (Opus). This prompt is designed to be completed in
ONE session, without follow-up prompts. Read the "How to work" section first and follow it to the letter.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a
beginner programmer who knows aerospace engineering and CFD theory. **This whole prompt must be finished in this one
session.** I will not send follow-up prompts, so:

1. **Start:** read `CLAUDE.md`, `docs/gap_register.md`, `docs/theory_manual.md` (sections 7 and 12),
   `docs/developer_guide.md`, the memory files, and skim `aeroflowsim/euler/`, `aeroflowsim/gui/steps/results.py`,
   `aeroflowsim/gui/vtk_view.py`, `aeroflowsim/result_io.py`, `aeroflowsim/project.py`, `validation/`. Then write a
   short plan in plain words (what you will build, in which order, how you will verify it) and **start working
   immediately: do not wait for my approval of the plan.**
2. **Do not stop to ask questions.** Every design decision that matters is made below. For anything else, choose what
   the best commercial CFD tools (ANSYS Fluent, STAR-CCM+, Tecplot, ParaView) do, improve on it where it is clumsy,
   explain the choice in one sentence in your final summary, and go on. The ONLY reasons to stop and ask: deleting a
   file or folder that is not yours from this session; adding a runtime dependency other than those pre-approved
   below; anything outward-facing other than the push, tag and GitHub release authorised in Part 9.
3. **Walk through the user's next actions for every feature** before calling it done (saved preference): what happens
   when the user stops, runs again, changes an input, re-meshes, reopens the project, switches units or theme, opens an
   old project, or uses the command line instead of the GUI? Each must behave like the best tool would. Write these
   walk-throughs into the tests.
4. **Flag anomalies yourself.** Whenever a number looks wrong, a convergence stalls, a test is flaky, a picture looks
   off, or a result disagrees with theory: investigate the cause, fix it if it is in scope, otherwise record it in the
   gap register with what you found, and list it in the final summary. Never tune a number to pass a reference.
5. **Work in steps and commit after each part** (clear messages, the attribution line of the session). Run long jobs
   (validation, big runs, installer builds) in the background and keep working meanwhile; never sit idle.
6. **Verify everything yourself:** unit tests, GUI tests (pytest-qt), validation, and screenshots of every new GUI page
   in light AND dark theme (make a reusable script `tools/screenshots.py` that opens a project, runs it and saves the
   pictures; keep it in the repo). Look at every screenshot and fix what is ugly, cut off, overlapping or unreadable.
7. **The conversation may be summarised automatically when it gets long. Keep going** until every "Done when" item
   below is checked off with evidence.
8. **At the very end** (Part 11): full fast tests, full validation, all result lines reported, docs and gap register
   updated, push, release, and write the next prompt file `docs/roadmap/speed.md` in the same style as this one,
   including everything you found that belongs to it.

## Context

Done before this prompt (see the gap register and git log): 1D / quasi-1D solvers; face-based `Mesh` (2D, axisymmetric,
3D-ready); structured and Gmsh meshes; shape library; geometry workspace (CAD-like 2D editing, named boundaries);
gas library and units system; 2D Euler solver stage: the finite-volume 2D / axisymmetric Euler solver (`aeroflowsim/euler/`),
boundary-condition table, live monitors, Stop keeps the flow, Run CONTINUES the current solution (iteration 159 after
158; "Start from scratch" begins again), validity checks and smart rules, nozzle / external / custom-geometry templates,
validation (2D Sod, Mach 2 wedge, Mach 6 cylinder + carbuncle test, N2 nozzle on six meshes), 9 of 9 validation cases
PASS. Known open points relevant here (do not lose them): the paper-style picture export, mirror about the axis and
streamlines are missing; the cylinder "shock roughness" metric does not separate the carbuncle-fix on/off runs (find a
better one); the nozzle total-pressure loss (2.5 %) is made at the sharp throat corner and does not fall clearly with
refinement; the validation suite takes about 1.5 h, too long for every CI push.

Out of scope here (they have their own prompts): speed, implicit time stepping and the triangle-mesh residual stall
(Speed stage); low-Mach preconditioning; adaptive mesh refinement; batch runs (parametric studies); unsteady flow and animations of
time (unsteady flow); viscous flow (Phase 4); 3D (Phase 3). Do not start them; if something here depends on them, note it.

## Goal

Make AeroFlowSim's results handling at least as complete as ANSYS Fluent's for 2D and axisymmetric steady flow, and
better where Fluent is clumsy; prove the solver's order of accuracy and widen the validation; generate a complete
report of any project; ship a Windows installer and the 2D alpha release (v0.2.0a1) on GitHub.

## Architecture decisions (made: follow them)

- **New package `aeroflowsim/post/` (no Qt, no VTK)** holds all post-processing logic, so the command line, scripts,
  the report and the later AI plugin can use it: `surfaces.py` (named surfaces), `fields.py` (derived fields and custom
  field functions), `integrals.py` (surface and volume reports), `xy.py` (data along surfaces), `sampling.py`
  (interpolation at points), `compare.py` (two results), `report.py` (HTML/PDF), `export.py` (CSV, VTU, Tecplot).
  The GUI only draws what `post/` computes. Follow the established pattern: logic tested without a window.
- **Cell to node values:** for smooth contours, streamlines and interpolation, nodes get the inverse-distance-weighted
  average of their cells; boundary nodes use the boundary-face values (ghost / wall states) so wall values are right.
  Keep cell values available ("Cell values" display option) for honest inspection.
- **Named surfaces** are stored in the project (`project.yaml`, key `surfaces`) and survive re-meshing (they are
  geometric definitions, re-evaluated on the current mesh). Types: boundary (patch), line (two points), rake (line with
  N seed points), point (probe), iso-line (field = value), axis-parallel line at x = c or y = c.
- **Report definitions** (Fluent's best idea, made simpler): a named quantity = (surface or volume, operation, field),
  e.g. "mass-weighted average of total pressure on outlet". They are stored in the project, evaluated after every run,
  and, when marked "monitor", evaluated during the run (live plot, report file CSV in `results/`) and optionally used
  as a convergence criterion (settled within a tolerance over a window, like the existing monitors).
- **Custom field functions:** formulas of existing fields and constants (`p / 101325`, `sqrt(u**2 + v**2)`,
  `rho * u`), parsed with Python's `ast` and a whitelist of operators and numpy functions (NEVER `eval` of raw text),
  units derived where possible, stored in the project, available everywhere a field is.
- **Solution snapshots:** a project keeps its current result plus any number of named snapshots
  (`results/snapshots/<name>/run.npz`), so the user can save "baseline", change inputs, run, and compare or go back.
- **Interpolation onto a new mesh:** when the mesh changed, Run offers (default) to start from the previous solution
  interpolated onto the new mesh (inverse-distance from the old cell centres, k nearest neighbours with scipy's cKDTree),
  or from scratch. This is Fluent's "interpolate data" made automatic.
- **Patch (initialisation regions):** before a fresh start the user may patch regions (box, circle, a workspace face)
  with given values (e.g. p, T, velocity), on top of the Initial solution. Stored in the project.
- **Report:** `post/report.py` writes a self-contained HTML file (pictures embedded as base64) and a PDF made with
  matplotlib (`PdfPages`: text pages with tables + figures); both from the command line too
  (`python -m aeroflowsim report "<project>.afsproj"`). No Qt in the report code.
- **Installer:** PyInstaller (one-folder build) + Inno Setup script, per-user install (no admin rights), Start-menu
  shortcut, `.afsproj` file association (double-click opens the project), uninstaller. Unsigned (SmartScreen shows a
  warning: document it). PyInstaller and Inno Setup are pre-approved as BUILD tools (not runtime dependencies).
- **No other new dependencies.** scipy (already used) provides cKDTree; matplotlib provides the PDF.

## Part 1 - Results data and fields (post/fields.py, post/sampling.py)

- Derived fields, computed on demand for any 2D result: velocity magnitude, Mach (exists), total pressure and
  temperature (exist), static and total enthalpy, entropy (exists), pressure coefficient Cp (external: from p_inf, q_inf;
  internal: p/p0), density gradient magnitude and numerical schlieren (exp(-k |grad rho| / max)), vorticity
  (dv/dx - du/dy), velocity divergence, normal Mach number to the flow direction (shock indicator), cell quality fields
  (from the mesh) and the residual of the last iteration per cell (helps find stalls).
- Gradients by the solver's least-squares operator (reuse `aeroflowsim/euler/gradients.py`).
- Custom field functions as decided above; errors reported in plain words (unknown name, bad syntax, wrong units).
- Cell to node averaging and point sampling (value at any (x, y): the containing cell, linear from its gradient).
- Every field in the user's display units in the GUI (the units system exists), SI everywhere inside.
- Tests: gradients of linear fields exact; vorticity of solid-body rotation = 2 omega; Cp of a known state; custom
  functions (good and malicious input: `__import__`, attribute access, lambdas must be refused).

## Part 2 - Surfaces, XY plots, integrals and report definitions (post/surfaces.py, xy.py, integrals.py)

- Named surfaces as decided above, created in the GUI by typing values or by clicking/dragging in the view (line by
  two clicks, point by one click), listed in a "Surfaces" panel (rename, delete, edit, show/hide in the view).
- Line surfaces sample the field at points along the line (cell crossing points, so the plot is exact per cell).
- XY plots (Fluent's XY plot, improved): y = any field (or several), x = position along x, y or arc length, or any
  field; on one or more surfaces; overlay of reference data from CSV (experiment, theory) with a legend; overlay of the
  same plot from snapshots or other projects; log axes; export CSV and PNG/SVG/PDF in paper style.
- Surface integrals on boundaries and lines (per metre depth planar, full circle axisymmetric): area, integral,
  area-weighted average, mass-weighted average, mass flow rate, flux of any conserved quantity, min, max, standard
  deviation; volume integrals over the domain or a region (box, circle, workspace face): volume, mass, volume-weighted
  average, min, max.
- Flux balance report (Fluent "Fluxes"): mass, momentum and energy in/out per boundary and the net imbalance.
- Forces and moments: any set of walls, any axis and moment point, pressure force (viscous later), in body and wind
  axes, coefficients with editable reference values; centre of pressure for 2D bodies.
- Report definitions + monitors + convergence criteria as decided above; the Run page shows user monitors next to the
  built-in ones; the report file CSV is written during the run and continues when a run is continued (2D Euler solver stage
  behaviour), and restarts with "Start from scratch".
- Tests: integrals of known fields on known surfaces (exact for linear fields); mass-flow report equals the solver's
  boundary flux; flux balance closes on a converged run; report definitions survive save/reopen and a re-mesh.

## Part 3 - Graphics (GUI, VTK view) at Fluent level and better

- Contours: filled (smooth from node values, or flat per cell), contour lines with chosen levels or number of levels,
  banded colours, labels on lines; colour map, range (auto, auto over the whole run history, from snapshot, typed,
  clip), log scale, colour bar (position, title, number format, units); "Mesh edges" and "Boundaries" overlays.
- Vectors: velocity (or any vector: gradients) as arrows, scale, skip / uniform density, colour by any field, fixed
  length option.
- Streamlines: from a rake, a line or clicked points, both directions, arrow marks, colour by field (VTK stream tracer
  on node data).
- Mirror about the axis or symmetry plane (display only) and 3D revolved view of axisymmetric results (surface of
  revolution coloured by the field: rotate with the mouse).
- Several views side by side (2 or 4): different fields, or the same field of two snapshots, with linked cameras.
- Saved scenes (named: field, colour map, range, overlays, camera) in the project; one click restores a scene.
- Picture export: PNG at a chosen resolution, transparent background option, paper style (light) whatever the theme,
  SVG/PDF for XY plots; copy to clipboard.
- Probe: click shows all values in Properties (exists); pin probes as point surfaces; hover tooltip with the field value.
- Right-click menus in the Results and Mesh views (gap register item): set as surface, probe here, zoom to fit, save
  picture, reset view.
- Histogram of a field (cell count or volume-weighted), with min/mean/max.
- Difference view: field of result A minus result B on the same mesh (snapshots) with a diverging colour map.
- Everything follows the theme and the units; check at 100 %, 125 % and 150 % display scaling (gap register item):
  nothing cut off.

## Part 4 - Run-workflow completion (Fluent parity)

- Solution snapshots (save, rename, delete with confirmation, restore as the current solution, compare).
- Interpolation onto a new mesh (decided above), with a test that a converged coarse solution interpolated onto a finer
  mesh converges in fewer iterations than from scratch and to the same answer.
- Patch regions for a fresh start (decided above).
- Report files of monitors and report definitions (CSV) in `results/`.
- Command line: `report`, `export` (fields, surfaces, XY data), `snapshot` subcommands; all post-processing usable from
  scripts (`aeroflowsim.post`), documented with examples.

## Part 5 - Exports (post/export.py)

- Fields: CSV (cell centres or nodes), VTU (exists: extend with node data and derived fields), Tecplot ASCII (.dat,
  FEPOLYGON or FEQUADRILATERAL zones, cell-centred via VARLOCATION), surfaces and XY data as CSV, report definitions
  table as CSV. All in SI, with units in the column names (GUI exports may use display units, as now).
- Tests: files re-read and compared (VTU via the existing writer's reader or a tiny parser; Tecplot header and counts).

## Part 6 - Verification: Method of Manufactured Solutions (CLAUDE.md rule 13)

- Smooth manufactured solution for rho, u, v, p (sums of sines and cosines with different wave numbers, all positive,
  mildly supersonic and subsonic regions); its source terms derived analytically and coded in numpy (write out the
  derivatives; no sympy); a source hook in the solver (cell source evaluated at the centroid: second-order accurate);
  an "exact" boundary condition (ghost = exact state at the face centre), internal to verification only.
- Order of accuracy (L1, L2, Linf of each variable) on 4 mesh levels (refinement ratio 2): structured quads, distorted
  quads, triangles, mixed, and the axisymmetric form (with its pressure source). First order and second order with no
  limiter (add limiter option "None"), and with Venkatakrishnan (expected: near 2 on smooth meshes, lower with the
  limiter on coarse meshes: report what you see). Acceptance: observed order of the second-order scheme >= 1.8 on
  structured, >= 1.7 on triangles/mixed at the finest pair; if not, find and fix the cause before going on.
- GCI tool `aeroflowsim/gci.py` (Roache): observed order, Richardson extrapolation, GCI fine/coarse, asymptotic range
  check; used in the MMS report and the nozzle study (replace the hand-written Richardson lines).
- MMS results in `validation/report.md` (a verification section) and in the theory manual.

## Part 7 - Validation suite (widen and speed up)

Add these cases, each with a `reference.toml` (value, source, tolerance) and `validate.py`, run through the one engine
and the templates, never tuned:
- **Diamond airfoil** (t/c = 0.1, Mach 2 or 3, alpha 0 and 2 deg) vs shock-expansion theory: Cl, Cd, surface
  pressures on each face.
- **Axisymmetric cone** (15 deg half-angle, Mach 2) vs Taylor-Maccoll: shock angle, surface Cp (compute the
  Taylor-Maccoll solution in `aeroflowsim/gasdynamics.py`, tested against tabulated values from NACA 1135).
- **Prandtl-Meyer expansion** round a convex corner (planar, Mach 2, 10 deg): downstream Mach number and pressure.
- **NACA 0012 transonic Euler**: Mach 0.8, alpha 1.25 deg (shock on both surfaces) and Mach 0.5, alpha 1.25 deg
  (subsonic: drag must tend to zero with refinement): Cl, Cd vs the grid-converged values of Vassberg & Jameson (2010),
  "In pursuit of grid convergence for two-dimensional Euler solutions", J. Aircraft 47(4) (look the values up and cite
  them with page/table; do not use memory), on a C-domain from the workspace, three meshes, with the GCI tool.
- **Experimental nozzle**: one converging-diverging nozzle with measured wall pressures from the NASA NPARC Alliance
  verification and validation archive (fetch the data file and its citation; store both in `validation/`), e.g. the
  Back, Massier & Gier (1965) conical nozzle, with the 2D axisymmetric solver; compare wall p/p0 along x (pointwise
  tolerance band, documented).
- **Carbuncle metric:** replace the cylinder "shock roughness" with a metric that separates fix on/off (e.g. the
  amplitude of the odd-even mode of the shock radius along the front, or the stand-off oscillation over the last N
  iterations), and assert that it does.
- **Sharp-throat total-pressure loss:** add the rounded-throat N2 nozzle (Rcu = 1.5, Rcd = 0.4) to the nozzle study and
  report the loss and Cd on both; state the finding in the report (expected: the loss is a corner effect).
- **CI speed:** a `quick` validation set (coarse meshes of every case, under 10 minutes) runs on every push; the full
  suite runs weekly (scheduled workflow) and on version tags. Report which set produced `validation/report.md`.
- **Rule 4 (never change validated numbers silently):** after every change, compare the report with the previous one;
  any changed number is explained in the commit and the final summary.

## Part 8 - Automatic report (post/report.py)

For any project (GUI: Results > Report..., command line: `report`): title page (project, template, date, AeroFlowSim
version, fingerprints for reproducibility), geometry picture, mesh statistics and quality, boundary-condition table,
gas and its sources, numerics, convergence history (residuals and monitors), key numbers and report definitions, flux
balance, validity checks with levels, contour pictures (default scenes: Mach, pressure, plus saved scenes), XY plots
(wall pressure / Cp, user plots), comparison with references (quasi-1D for nozzles, theory where the template has it),
snapshots comparison if chosen, and a "how to reproduce" section. HTML self-contained and PDF; in the user's units in
the GUI, SI from the command line (state the units on the page). Test: report of each template builds and contains its
sections; HTML has no external links (privacy rule 12).

## Part 9 - Installer, documentation and the 2D alpha release

- Installer as decided above, built by a script `tools/build_installer.py` and by a GitHub Actions workflow on version
  tags (windows-latest), with a smoke test of the installed program (`--version`, a headless `run` of the Sod case, the
  GUI starts and closes). Document the build, the size, and the SmartScreen warning.
- Documentation: user guide `docs/user_guide.md` (install, first project, every step page, post-processing tools,
  report, units, keyboard shortcuts, where files live, troubleshooting), three new tutorials (post-processing a nozzle:
  surfaces, XY plots, report definitions, report; NACA 0012 transonic: C-domain, monitors, Cp plot, GCI; experimental
  nozzle comparison), the theory manual (derived fields, integrals and weighting, interpolation, MMS and GCI, the new
  validation cases), the developer guide (`post/` architecture, how to add a derived field / surface type / report
  section), `CHANGELOG.md`, `CONTRIBUTING.md` (short), README with screenshots.
- Version 0.2.0a1 in `pyproject.toml` and `aeroflowsim/__init__.py`; `requirements.txt` exact versions.
- **Authorised:** push to `main`, create the tag `v0.2.0a1` and a GitHub release with the installer and release notes
  (what works, known limitations from the gap register, how to report problems). Mark it as a pre-release.
- Streamlit GUI: do NOT delete it. Write `docs/parity_checklist.md` (every Streamlit feature and where it is in the
  desktop GUI) so I can confirm parity; removal is a later step with my OK.

## Part 10 - Quality gates (all must hold before the release)

- Fast tests pass on Windows (and CI Ubuntu); GUI tests pass; quick validation passes; full validation passes with
  every number explained if it changed.
- No regression of the 2D Euler solver stage behaviour: Stop keeps the flow, Run continues (159 after 158), Start from scratch, results
  of an older mesh never painted on a new one, angle of attack refused on axisymmetric meshes.
- Every new GUI page: screenshots light and dark at 100 % and 150 % scaling, looked at and fixed.
- Privacy test still passes (no network, no web addresses in the GUI or reports).
- `python -m aeroflowsim run` and `report` work without Qt (test with Qt blocked, as the existing test does).

## Part 11 - Finish

- Update `docs/gap_register.md` (every item that moved, every new gap or anomaly found), `CLAUDE.md` layout (new
  modules), the theory manual and the developer guide.
- Run the full fast tests and the full validation; report the result lines.
- Commit, push, tag, release (Part 9).
- Write `docs/roadmap/speed.md` (speed: Numba, implicit LU-SGS, multi-core; the triangle-mesh residual stall; the
  wall-clock targets; anything you found) in the same style as this file, so it too can be done in one session.
- Final message to me, in plain words: what was built (by part), the verification table (MMS orders, every validation
  case with reference, result, error, pass/fail), what changed from this plan and why, anomalies found and what was
  done about each, the plain-language walkthrough of the most important new module (CLAUDE.md rule 15: what it does,
  key equations, where they are in the code), and the link to the release.

## Done when (check every line with evidence in the final message)

1. In the GUI I can, on my N2 nozzle and on a NACA 0012: show filled and line contours, vectors and streamlines;
   mirror and revolve the axisymmetric nozzle; create line, rake, point and iso-line surfaces by typing or clicking;
   plot any field along them with reference data overlaid; compute surface and volume integrals and the flux balance;
   define report definitions, watch them live during a run and use one as a convergence criterion; make a custom field
   function; save scenes; show two snapshots side by side and their difference; export pictures, CSV, VTU and Tecplot;
   interpolate a solution onto a new mesh; patch an initialisation region; generate the HTML and PDF report.
2. MMS shows second order (acceptance values above) on all mesh types and in axisymmetric form, with GCI.
3. All validation cases above pass (or a documented, explained, non-tuned shortfall is reported as an anomaly), the
   quick set runs on every push and the full set weekly and on tags.
4. The installer installs, starts AeroFlowSim, opens a double-clicked `.afsproj`, and uninstalls cleanly; v0.2.0a1 is
   released on GitHub with the installer.
5. User guide, tutorials, theory manual, developer guide, gap register, CHANGELOG, parity checklist updated.
6. `docs/roadmap/speed.md` written.
7. Fast tests and validation pass; result lines reported; everything pushed.


---

## Progress log

If the session was summarised or interrupted: re-read this file and `CLAUDE.md`, then continue with "Next".
Order of work (addendum A): Part 6 → Parts 1-2 → Part 7 → Part 3 → Parts 4-5 → Part 8 → Part 9 → Parts 10-11.

## Done

| Part | What | Commit | Verified by |
|---|---|---|---|
| 6 | MMS (`aeroflowsim/mms.py`), solver hooks (source, boundary face values), limiter "None", smooth mesh warp, GCI tool, `validation/mms_euler2d`, quick/full validation sets | 4d355c6 | `tests/test_mms_gci.py`; full study 16-128: L2 order 1.98-2.02 on quads, distorted quads, triangles, mixed, planar + axisymmetric (all PASS) |
| 1-2 | `aeroflowsim/post/` (solution, fields + safe formulas, sampling, surfaces, integrals, flux balance, forces, report definitions + monitors + CSV writer), project settings, run extras (monitors, patches, interpolation) | 4d355c6, c51ff89 | `tests/test_post.py` (29), `tests/test_post_project.py` (8; stop/continue/scratch CSV walk-through, convergence criterion, snapshots, exports, patches; interpolation test marked validation) |
| 4-5 | snapshots, compare, export (CSV/VTU node data/Tecplot), XY data, CLI `report`/`export`/`snapshot` | c51ff89 + later | tests above, `tests/test_report.py` |
| 7 | diamond, cone, Prandtl-Meyer, NACA 0012 (Vassberg & Jameson Table 10/11 fetched), BMG nozzle (JPL TR 32-654 fetched, Fig. 4 digitized), carbuncle metric, rounded throat + GCI in nozzle study, Taylor-Maccoll/shock-expansion/PM theory | d4b1519 + later | quick runs: diamond 7/7 within 0.4 %, PM 0.66 %/0.05 %, cone Cp 0.09 %, BMG 8/9 points (z = 2.24 in SHORTFALL explained) |
| 3 | Results workspace: display scenes, contours/lines/vectors/streamlines/mirror/revolve, 1/2/4 linked views, surfaces by click, reports, XY plot in Plots area, snapshots compare, custom fields, histogram, pictures, right-click, hover; Run start options | d4b1519 | `tests/gui/test_post_gui.py` (7) + all GUI tests (64 pass); screenshots via `tools/screenshots.py` |
| 8 | `post/report.py` HTML + PDF, `post/pictures.py`, CLI report, GUI Tools > Project report | (this commit) | `tests/test_report.py` (3 templates, sections, no web addresses, Qt blocked) |
| 9 | installer (PyInstaller + Inno Setup, per user, .afsproj association via `project.afsproj`, uninstaller), smoke test, THIRD_PARTY_LICENSES.txt, workflows (tests quick set, weekly full validation, installer on tags), user guide, 3 tutorials, theory manual section 13, developer guide, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue templates, parity checklist, examples + start page, diagnostics + log + error dialog, version 0.2.0a1 | (this commit) | first build 166 MB, smoke test passed (version fix after) ; silent install + registry checked |

## Next

1. Fast tests (running), commit.
2. Full validation in the background (`run_all.py --jobs 3`), compare with `report_before.md` (rule 4), update theory-manual MMS table from `last_study.json`.
3. Dark + 150 % screenshots, fix what is ugly.
4. Final installer build + install / double-click / uninstall test; README screenshots, `docs/showcase/`.
5. Gap register, CLAUDE.md layout, `docs/roadmap/speed.md` + `next_steps.md`, push, tag, release (only if the gates hold).

## Decisions

- Validation folders whose "case" is not a template use `case = "aeroflowsim/<module>.py"`.
- Quick set writes `validation/report_quick.md`, full set `validation/report.md`; references may have `tolerance_percent_quick` and `shortfall` (status SHORTFALL: shown with its explanation, not counted as failure).
- Mass-weighted average uses rho |V.n| (Fluent). Boundary fluxes in post-processing are the solver's stored final fluxes.
- Cone reference: Sims 1964 (NASA SP-3004, tabulated) instead of the charts of NACA 1135.
- Cone shock angle: half-level crossing (tested against the maximum density gradient, the 5 % foot and M_n = 1 on the fine mesh: only the half-level crossing converges to the exact angle: 35.05 deg coarse, 34.21 deg fine, exact 33.91 deg); quick-set tolerance 4 % for the coarse mesh.
- .afsproj association: every project folder gets a small file `project.afsproj`; double-clicking it opens the folder.
- `run_all.py` runs cases sequentially by default (`--jobs N` parallel).

## Open anomalies

- Diamond airfoil: residual stalls ~4e-3 at the lower leading-edge shock foot (limiter limit cycle); Cl, Cd steady to 1e-6. Speed stage.
- Venkatakrishnan limiter loses order under refinement on smooth flows (MMS, triangles ~0.7-1.0). Gap register.
- BMG z = 2.24 in: 0.80 vs 0.87 measured, mesh-converged; cause not settled (steep gradient + position uncertainty, tap size). Gap register.
- Interpolated start only ~8 % fewer iterations (residual normalisation by the first iterations). Gap register.
- NACA 0012 Cl: SHORTFALL (study design: meshes not refined systematically; speed stage).
- Quick set: passes but takes about 32 min (target 10 min; NACA 9.5, quasi-1D 5.6, nozzle 5, diamond 4.5 min): the speed stage.
- Full validation 26 Oct: 15 of 15 cases pass with 2 explained shortfalls (BMG z = 2.24 in, NACA 0012 Cl); all 72 earlier validated numbers unchanged (rule 4). Validation results are now kept per case (validation/results/*.json) so single cases can be re-run and the report rebuilt.
- Two idle Python processes of an earlier parallel validation run could not be stopped (permission); they finished by themselves.
