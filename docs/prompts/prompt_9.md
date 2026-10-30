# Prompt 9 - 3D geometry workspace and 3D meshes (STEP, tetrahedra, prism inflation)

Model: Opus (many design decisions: 3D CAD handling, picking, mesh quality in 3D).
Designed for 3-4 sessions (9-1 ... 9-4). Paste everything below the line into a NEW Claude Code session for each
session, followed by "This is session 9-N" (the first: 9-1). Continue a stopped session with:
"continue Prompt 9 from docs/prompts/9_progress.md".

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a beginner
programmer who knows aerospace engineering and CFD theory. My weekly Claude limit is tight, so:

1. Start: read `CLAUDE.md`, `docs/gap_register.md`, `docs/prompts/9_progress.md` (the ledger; create it in 9-1),
   `docs/developer_guide.md` (geometry workspace, VTK view, jobs), `docs/theory_manual.md` sections 12-13d,
   `docs/prompts/8_progress.md` (what Prompt 8 left), and skim `aeroflowsim/geometry_model/`, `aeroflowsim/gui/geometry_*.py`,
   `aeroflowsim/gui/vtk_view.py`, `aeroflowsim/workspace_mesh.py`, `aeroflowsim/gmsh_mesh.py`, `aeroflowsim/mesh.py`,
   `aeroflowsim/mesh_io.py`, `aeroflowsim/inflation_layers.py`. Write a short plan in plain words and start at once.
2. Do not stop to ask questions (decide like Fluent Meshing, SpaceClaim, Pointwise, Gmsh would; one sentence why in the
   summary). Stop only before: deleting files not yours from this session, adding a dependency, anything outward-facing
   except the push at the end of each session.
3. **Stop and split rule:** each session does the parts listed for it below. If a session runs out of room, stop at
   the end of a part, commit, write the ledger (what is done, verified how, what is next, anomalies), and say so.
   Never leave a part half-done without a ledger entry.
4. Long jobs (meshing studies, validation) in the background, one heavy job at a time (the 32 GB machine ran out of
   memory with three at once in Prompt 8). Report result lines only.
5. Commit after each part. Flag anomalies yourself; never tune a number to pass.
6. Walk through the user's next actions for every feature (undo/redo, edit and re-mesh, change a size, reopen the
   project, old 2D project, units and theme, command line, Stop/Cancel a long mesh job) and write them into tests.

## Context (state after Prompt 8, release v0.2.0a2 if its gate held)

* 2D/axisymmetric solver: Numba kernels on all cores, implicit LU-SGS by default (default N2 nozzle converges in about
  20 s), MMS order 2. The face-based `Mesh` (`aeroflowsim/mesh.py`) and the solver are 3D-ready: hexahedra and tetrahedra
  are tested on single cells (`tests/test_euler_core.py`, `tests/test_kernels.py`); kernels handle dim = 3.
* The 2D geometry workspace (`geometry_model/`, history of operations replayed in OpenCASCADE through Gmsh `occ`, stable
  edge ids, boundary names by clicking) is the model to extend; `kernel.py` is the only file talking to OCC.
* Mesh import already reads 3D files (Gmsh v2/v4, SU2, CGNS, Fluent), see `mesh_io.py`.
* Not done and out of scope here: the 3D solver run itself (Prompt 10), multiple zones (Prompt 10).

## Decisions (made: follow them)

* 3D geometry = the same history-of-operations document as 2D, with 3D operations (import STEP/IGES solid, primitive
  bodies: box, cylinder, sphere, cone, revolve of a 2D profile, extrude; booleans; enclosure box/cylinder/sphere;
  face naming; refinement regions box/sphere/cylinder). Stable FACE ids across edits (lineage, as edges in 2D).
* Picking in 3D: faces (and edges for sizes) with the mouse in the VTK view, box selection, hide/show/isolate bodies,
  section plane. Own look (no ANSYS clone). Undo/redo for every edit.
* Meshes: Gmsh 3D tetrahedra with prism inflation layers from named walls (first-layer height from the smart rule
  y+ / Re), size fields from refinement regions and curvature; quality metrics (skewness, aspect ratio,
  non-orthogonality, volume ratio) in 3D, and the mesh checks (negative volume = error) before any run.
* The axisymmetric 2D templates stay as they are; a 3D template (`cases/external_3d`, mesh-only until Prompt 10:
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
   tutorial "sphere in a box" and "nozzle STEP to mesh", gap register, CHANGELOG, `docs/prompts/prompt_10.md` (3D Euler).
8. Full fast tests, GUI tests, quick and full validation; push.

## Quality gates (each session)

* Tests pass; validation of the session's parts written and passing; ledger updated; pushed.
* No GUI code in `geometry_model/` or `workspace_mesh.py`; no Qt in logic modules (tested).
* Privacy test still passes (no network code outside `assistant/net.py`).

## Done when (check every line with evidence)

1. A STEP body or primitives can be combined, enclosed, named and meshed (tetrahedra + prisms) from the GUI, with undo.
2. Volumes/areas/face ids are validated; 3D mesh quality checks run before any run.
3. Old 2D projects open and re-mesh unchanged; all tests and validation pass; docs, gap register, CHANGELOG, ledger and
   `prompt_10.md` written; pushed.
