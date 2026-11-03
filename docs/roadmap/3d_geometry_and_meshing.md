# 3D geometry and meshing - 3D geometry workspace and 3D meshes (STEP, tetrahedra, prism inflation)

Model: Opus (many design decisions: 3D CAD handling, picking, mesh quality in 3D).
Designed for 3-4 sessions (9-1 ... 9-4). Paste everything below the line into a NEW Claude Code session for each
session, followed by "This is session 9-N" (the first: 9-1). Continue a stopped session with:
"continue the 3D geometry and meshing stage from docs/roadmap/3d_geometry_and_meshing.md".

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a beginner
programmer who knows aerospace engineering and CFD theory. My weekly Claude limit is tight, so:

1. Start: read `CLAUDE.md`, `docs/gap_register.md`, `docs/roadmap/3d_geometry_and_meshing.md` (the ledger; create it in 9-1),
   `docs/developer_guide.md` (geometry workspace, VTK view, jobs), `docs/theory_manual.md` sections 12-13d,
   `docs/roadmap/speed.md` (what speed stage left), and skim `aeroflowsim/geometry_model/`, `aeroflowsim/gui/geometry_*.py`,
   `aeroflowsim/gui/vtk_view.py`, `aeroflowsim/workspace_mesh.py`, `aeroflowsim/gmsh_mesh.py`, `aeroflowsim/mesh.py`,
   `aeroflowsim/mesh_io.py`, `aeroflowsim/inflation_layers.py`. Write a short plan in plain words and start at once.
2. Do not stop to ask questions (decide like Fluent Meshing, SpaceClaim, Pointwise, Gmsh would; one sentence why in the
   summary). Stop only before: deleting files not yours from this session, adding a dependency, anything outward-facing
   except the push at the end of each session.
3. **Stop and split rule:** each session does the parts listed for it below. If a session runs out of room, stop at
   the end of a part, commit, write the ledger (what is done, verified how, what is next, anomalies), and say so.
   Never leave a part half-done without a ledger entry.
4. Long jobs (meshing studies, validation) in the background, one heavy job at a time (the 32 GB machine ran out of
   memory with three at once in the speed stage). Report result lines only.
5. Commit after each part. Flag anomalies yourself; never tune a number to pass.
6. Walk through the user's next actions for every feature (undo/redo, edit and re-mesh, change a size, reopen the
   project, old 2D project, units and theme, command line, Stop/Cancel a long mesh job) and write them into tests.

## Context (state after the speed stage, release v0.2.0a2 if its gate held)

* 2D/axisymmetric solver: Numba kernels on all cores, implicit LU-SGS by default (default N2 nozzle converges in about
  20 s), MMS order 2. The face-based `Mesh` (`aeroflowsim/mesh.py`) and the solver are 3D-ready: hexahedra and tetrahedra
  are tested on single cells (`tests/test_euler_core.py`, `tests/test_kernels.py`); kernels handle dim = 3.
* The 2D geometry workspace (`geometry_model/`, history of operations replayed in OpenCASCADE through Gmsh `occ`, stable
  edge ids, boundary names by clicking) is the model to extend; `kernel.py` is the only file talking to OCC.
* Mesh import already reads 3D files (Gmsh v2/v4, SU2, CGNS, Fluent), see `mesh_io.py`.
* Not done and out of scope here: the 3D solver run itself (3D Euler solver stage), multiple zones (3D Euler solver stage).

## Decisions (made: follow them)

* 3D geometry = the same history-of-operations document as 2D, with 3D operations (import STEP/IGES solid, primitive
  bodies: box, cylinder, sphere, cone, revolve of a 2D profile, extrude; booleans; enclosure box/cylinder/sphere;
  face naming; refinement regions box/sphere/cylinder). Stable FACE ids across edits (lineage, as edges in 2D).
* Picking in 3D: faces (and edges for sizes) with the mouse in the VTK view, box selection, hide/show/isolate bodies,
  section plane. Own look (no ANSYS clone). Undo/redo for every edit.
* Meshes: Gmsh 3D tetrahedra with prism inflation layers from named walls (first-layer height from the smart rule
  y+ / Re), size fields from refinement regions and curvature; quality metrics (skewness, aspect ratio,
  non-orthogonality, volume ratio) in 3D, and the mesh checks (negative volume = error) before any run.
* The axisymmetric 2D templates stay as they are; a 3D template (`cases/external_3d`, mesh-only until the 3D Euler solver stage:
  `solver = false` + message) joins the discovery automatically.
* Size of the test meshes: keep the tests under a minute each (coarse meshes); bigger meshes in the validation.

## Parts and sessions

**Session 9-1 - document and kernel (no GUI yet)**
1. 3D operations in `geometry_model` (STEP/IGES import, primitives, revolve, extrude, booleans, enclosure), stable face
   ids, face naming; `history.json` with a version field; old 2D histories load unchanged (test).
2. Validation without a solver (`validation/geometry_3d/`): volumes and surface areas of primitives and booleans against
   exact formulas; a STEP round trip; face ids stable after an upstream edit.

**Session 9-2 - 3D meshes**
3. `workspace_mesh.py` 3D path: Gmsh tetrahedra + prism layers from named walls, size fields, refinement regions;
   patches = face names; the face-based `Mesh` with VTK cell types; save/load; mesh export (Gmsh, SU2, CGNS).
4. 3D mesh quality in `mesh_quality.py` and the mesh checks; a mesh study (validation: cell count vs size, first-layer
   height reached, total volume of the fluid = enclosure - body to 0.1 %).

**Session 9-3 - GUI**
5. Geometry step in 3D: VTK view with face picking, box selection, hide/show, section plane, revolve/extrude dialogs,
   boundary naming table, refinement regions, all undoable; logic without Qt in `gui/geometry_logic.py` (tests).
6. Mesh step in 3D: show the surface mesh and a cut through the volume mesh, quality histograms, worst cells; Stop and
   Cancel of a long Gmsh job; the `external_3d` template (mesh-only).

**Session 9-4 - finish (if needed)**
7. Docs (user guide: 3D workspace and meshing; theory manual: prism layers, 3D quality metrics; developer guide),
   tutorial "sphere in a box" and "nozzle STEP to mesh", gap register, CHANGELOG, `docs/roadmap/3d_euler_solver.md` (3D Euler).
8. Full fast tests, GUI tests, quick and full validation; push.

## Quality gates (each session)

* Tests pass; validation of the session's parts written and passing; ledger updated; pushed.
* No GUI code in `geometry_model/` or `workspace_mesh.py`; no Qt in logic modules (tested).
* Privacy test still passes (no network code outside `assistant/net.py`).

## Done when (check every line with evidence)

1. A STEP body or primitives can be combined, enclosed, named and meshed (tetrahedra + prisms) from the GUI, with undo.
2. Volumes/areas/face ids are validated; 3D mesh quality checks run before any run.
3. Old 2D projects open and re-mesh unchanged; all tests and validation pass; docs, gap register, CHANGELOG, ledger and
   `3d_euler_solver.md` written; pushed.

---

## Progress log (ledger)

The stage was done as ONE session (prompt 9, all 8 parts) instead of the 4 sessions planned above.

### Part 1 - 3D operations, stable face ids, history version (done)
- New: `geometry_model/kernel3d.py` (Kernel3D: solids in OCC, face lineage by projecting probe points of every new
  face onto COPIES of the old faces), `operations3d.py` (box, cylinder, cone, sphere, STEP/IGES import, revolve of a
  profile or a nozzle wall CSV, extrude, transform, boolean, fluid/solid, delete, enclosure box/cylinder/sphere with
  half-domain symmetry plane, face names, refinement box/sphere/cylinder, template body + template far field),
  `built3d.py` (BuiltGeometry3D: bodies, faces, edges, names, regions). `document.py`: `dimension` (2 or 3);
  3D documents are saved as format 2 with `"dimension": 3`; 2D documents are written byte-for-byte as before
  (format 1, no dimension key), so old projects keep their fingerprints. STEP export (`export.py`) writes solids.
- Verified: `tests/test_geometry_3d.py` (15 tests: old 2D history loads and saves unchanged, 3D round trip, newer
  format refused, primitives, revolve/extrude, nozzle wall CSV revolve, booleans, pieces "#n", transforms, enclosures
  incl. half domain, names after upstream edits, refinement, drawing triangulation, STEP round trip, units).
  Existing 2D geometry tests: 55 passed.
- Anomaly found and fixed: OCC renumbers ALL faces of a transformed body in 3D (even one translate; volumes keep
  their numbers). Transform3D therefore applies the same transformation to the lineage copies and relabels.
- Next: part 2 (validation/geometry_3d).

### Part 2 - validation without a solver (done)
- `validation/geometry_3d/` (24 references): volumes and areas of box, cylinder, sphere, truncated cone, box minus
  corner sphere, box united with a half sphere, sphere intersected with a half space, revolved frustum, extruded
  prism, box enclosure around a sphere, STEP round trip (volume, area, number of faces), and 3 named faces staying on
  the right faces after upstream edits (resized box, smaller sphere, inserted move).
- Verified: all pass; errors 0 to 9e-15 relative (tolerance 1e-6 %: OCC integrates the exact surfaces).
- Next: part 3 (3D meshing path in workspace_mesh.py).

### Part 3 - 3D meshing path (done)
- New: `aeroflowsim/workspace_mesh3d.py` (mesh_3d: replay, checks, size fields Distance/Threshold from walls + Gmsh
  curvature + Box / Ball / capsule-of-balls for cylinder regions, surface mesh, prism layers, Delaunay tetrahedra,
  face-based Mesh with VTK types 10 and 13, patches = face names) and `aeroflowsim/prism_layers.py` (grow_prisms:
  angle-weighted node normals, mitre stretch at wall edges, columns kept in flat neighbouring planes, smoothing until
  no prism is inverted). `workspace_mesh.mesh_for` sends every 3D template (case.workspace_settings_3d) there.
  `mesh_io.py`: 3D export (Gmsh 2.2 and 4.1, SU2, CGNS; VTK -> Gmsh/CGNS prism order).
- Method (decision): grow the layers first, then give Gmsh the TOP of the layers as the walls' surface mesh, and mesh
  a flat neighbouring boundary (symmetry, inlet, outlet) again in its plane with its edge at the top of the layers.
  Same idea as the 2D inflation; Gmsh's own 3D boundary-layer extrusion needs the built-in (not OCC) kernel.
- Verified: `tests/test_workspace_mesh3d.py` (10 tests, 4 s): tets only, prisms = layers x wall triangles, volume with
  layers = without (same facets, 1e-10), first layer height 0.005 m reached (mean within 3 %), save/load, half domain
  (quads on y = 0), nozzle (side quads exactly on the inlet / outlet planes), refinement region, refusals (no fluid,
  unnamed faces, curved neighbour of an inflation wall, too many cells), estimate within x4, export read back by Gmsh
  (element counts, physical names, minDetJac > 0 for prisms), SU2 and CGNS contents.
- Anomalies: (1) Gmsh renumbers nodes after meshing unless Mesh.Renumber = 0 (needed: the layer nodes refer to them).
  (2) The stage plan said mesh IMPORT reads 3D files; it does not (`mesh_io` reads 2D only) -> gap register, 3D Euler
  solver stage. (3) Layers next to a CURVED non-wall boundary are refused with a message (gap register).
- Next: part 4 (3D quality metrics, checks, mesh study).

### Part 4 - 3D mesh quality, checks, mesh study (done)
- `mesh_quality.py`: equivolume skewness (1 - V / V_ideal of the circumsphere, Fluent's tetrahedron skewness), smallest
  dihedral angle, `skewness` (equivolume for tetrahedra, equiangle otherwise: 2D numbers unchanged),
  `QUALITY_COLORINGS_3D` + `colorings(mesh)`; quality_summary adds min_dihedral_angle for meshes with tetrahedra.
- `checks.py`: skewness check of a 3D mesh (warning above 0.95), dihedral-angle check (warning below 5 deg), first
  layer height check (measured V/A of the wall prisms vs requested, warning beyond 20 %), volume-ratio limit 10 for
  meshes with tetrahedra (documented why). The negative-volume error check already ran before any solver.
- `validation/mesh_3d/` (15 references): sphere D = 1 m in a 16 x 11 x 11 m box, 5 prism layers, three levels:
  fluid volume to 0.000 % (tol 0.1 %), wall area 0.55 / 0.15 / 0.04 % low (faceting), first layer 0.4 % high, all
  cells positive, no error check. Full set 44 s. Study table: cells per level and quality numbers.
- Verified: 3 more tests in `tests/test_workspace_mesh3d.py` (regular / corner / sliver tetrahedron metrics, 3D mesh
  checks, inverted cell = error): 13 pass; tests/test_checks.py passes (2D unchanged).
- Next: part 5 (Geometry step in 3D).

### Part 5 - Geometry step in 3D (done)
- New: `gui/steps/geometry3d.py` (Geometry3DPage: tool bar Select / Box select, Bodies, Import STEP/IGES, Edit,
  Enclosure, Name boundary, Refinement, Hide / Isolate / Show all, Section x/y/z + slider, Suggestions; History,
  Boundaries and Dimensions tabs; right-click menu), `gui/geometry3d_view.py` (Geometry3DView: faces in boundary
  colours, edges, regions, axes, standard views, vtkCellPicker face picking, rubber-band box selection with the CAD
  rule left-to-right inside / right-to-left touching). `gui/steps/geometry.py` shows it in a QStackedWidget for 3D
  templates. Logic without Qt appended to `gui/geometry_logic.py` (FIELDS for every 3D operation incl. point lists in
  mm, operation_for_3d, boundary rows / rename / type / prism layers, suggestions_3d, Visibility, section_plane,
  faces_in_rectangle, toggle_selection, texts). 3D smart rules `smart_rules.suggestions_3d` (wall size L/40 and 1/4 of
  the shortest wall edge, largest size, y+ first layer). 3D geometry checks (`checks.GEOMETRY_CHECKS_3D`).
  New icons (body, box_select, hide, show, isolate, section).
- Decisions: hide / isolate / section are view settings (not undone), as in SpaceClaim / Fluent Meshing; an imported
  solid replaces the template body (and its far field when imported as fluid); suggested walls get the prism tick so
  the template's inflation input switches them.
- Verified: `tests/test_geometry_logic_3d.py` (9 tests, no Qt), `tests/gui/test_geometry3d_gui.py` (7 tests in the real
  window: face click, hide then pick the face behind, box select of everything, isolate, section then pick the inner
  sphere, add box + union, name by stable id, undo / redo, upstream diameter change keeps the name, save + reopen,
  rename / type / prism layers, theme switch, units, a 2D project afterwards and back). Whole GUI suite: 86 passed.
- Next: part 6 (Mesh step in 3D, template).

### Part 6 - Mesh step in 3D, template external_3d (done)
- `cases/external_3d` (mesh only: solver = false + message; body sphere / cylinder / nose cone / box, far field box /
  cylinder / sphere, half domain, mesh and prism inputs in L, free stream for the y+ rule), discovered automatically;
  case contract documents workspace_settings_3d / body_3d / domain_3d. Example STEP `examples/conical_nozzle.step`.
- Mesh step: `MeshView.show_mesh_3d` (boundary faces in patch colours or by the field of their cells; cut x / y / z
  shows the whole cells the plane passes through, far-side faces see-through), 3D cell / face picking, worst cell
  (zoom), colour list per mesh (3D adds equivolume skewness and dihedral angle), log histogram of the field, 3D rows in
  the summary. *Export mesh…* writes .vtu / .msh / .su2 / .cgns (`mesh_io.write_mesh`), CLI `export <project> --mesh`.
- Fix found here: a cone's apex made Gmsh's curvature rule ask for cells of size 0 (37 s, then "identical points"):
  minimum cell size = 1/10 of the smallest requested size (`MIN_SIZE_FRACTION`).
- Verified: `cases/external_3d/test_case.py` (8 tests: every body with the exact fluid volume, prisms + half domain,
  estimate, y+ suggestion, the nozzle STEP tutorial), GUI test of the 3D Mesh step (cut, histogram, worst cell, checks)
  and of Cancel during a long 3D Gmsh job; CLI `run` of a 3D project and `export --mesh` to four formats.
- Next: part 7 (docs, tutorials, gap register, CHANGELOG, next stage plan).

### Part 7 - docs (done)
- User guide "3D geometry and meshing"; theory manual 13e (3D face lineage), 13f (prism layers: column heights,
  angle-weighted normals, mitre stretch, plane constraint, validity), 13g (equivolume skewness, dihedral angle, checks)
  + references; developer guide "The 3D geometry workspace and 3D meshes"; tutorials `sphere_in_a_box.md` and
  `nozzle_step_to_mesh.md` (the latter is a test); gap register (3D rows done, new gaps: edge picking / sizing, layers
  next to curved non-wall boundaries, layer thinning in gaps, 3D fillet / chamfer, 3D plume / plenum helpers, faster
  meshing, 3D mesh import (finding), CSV revolve uses straight segments); CHANGELOG; CLAUDE.md layout;
  `docs/roadmap/3d_euler_solver.md` (one-session plan with this stage's findings) and the roadmap README.
- Next: part 8 (full fast tests, GUI tests, quick and full validation, push).

### Part 8 - full tests, validation, push (done)
- Fast tests 984 passed; GUI tests 86 passed (1 skipped), 3D GUI tests re-run after the last view change: 7 passed.
- Quick validation 18 of 18 pass; full validation all pass. 2D numbers in report.md unchanged (only wall-clock times
  differ); the quick report's 2D differences date from the speed stage (it was last written with 0.2.0a1).
- Old 2D project made with the pre-stage code: opens with mesh status ok and re-meshes node-for-node identically.
- Pushed. Next stage: `docs/roadmap/3d_euler_solver.md`.
