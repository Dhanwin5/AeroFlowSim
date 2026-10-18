# Body in a free stream, mesh (`external_2d`)

The mesh of the flow around a body: a planar 2D body (1 m deep) or an axisymmetric body, inside a
far-field boundary. It needs the optional Gmsh mesher (`pip install -e ".[mesh]"`); without it, the
GUI says how to install it.

**Status:** mesh only (`solver = false` in `schema.toml`). The 2D / axisymmetric Euler solver
arrives in Prompt 7 and will use these meshes unchanged.

**Angle of attack is not part of the mesh.** The body always sits at zero angle, with its front at
x = 0 and its axis (or chord line) on y = 0. The flow direction will be set in the solver (Prompt 7),
so one mesh serves every angle of attack (full domain only: a half domain needs zero angle).

## Shapes

The **Shape** dropdown and the shape inputs come from the shape library (`aeroflowsim/shapes/`,
`shape_library = true` in `schema.toml`): wedge, diamond airfoil, NACA 4-digit airfoil, circular
cylinder, conical nose cone (flat base or cone-cylinder, axisymmetric) and a custom coordinates file
(Selig or Lednicer `.dat`, or CSV x,y; planar or axisymmetric). See CONTRIBUTING.md for adding one.

Every shape gives its **reference length** (chord, length or diameter) and **reference area**
(planar: reference length × 1 m; axisymmetric: base area π R²), shown in the Setup tab and stored in
the mesh (`mesh.info["reference_length"]`, `mesh.info["reference_area"]`) for Cl, Cd and Cm later.

## Domain

- **Circle** (default): radius 20 reference lengths, centred on the middle of the body. The circle
  is split into at least 120 faces so it stays round (area 0.05 % too small at 120 faces).
- **Rectangle**: 10 reference lengths upstream of the body, 20 downstream, 10 above and below.
- **Half domain**: only y ≥ 0, for bodies symmetric about y = 0 at zero angle, with a `symmetry`
  patch on y = 0. Axisymmetric bodies always use the half domain, with an `axis` patch on y = 0.
- Patches: `wall` (the body), `farfield`, and `symmetry` or `axis`.

## Mesh (`aeroflowsim/gmsh_mesh.py`)

All sizes are multiples of the reference length, so the defaults fit any body size.

- Triangles, or quad-dominant (triangles recombined into quads).
- Cell size h(d) = min(far-field size, surface size + (growth − 1) d) at distance d from the body;
  default surface size L/200, far-field size 2 L, growth 1.2.
- Edge refinement (on by default): 4 times smaller cells at sharp corners and leading/trailing edges.
- Inflation layers (off by default): quad layers grown from the body (first layer 1e-6 L, 10 layers,
  growth 1.2), with fans at sharp corners (`aeroflowsim/inflation_layers.py`). With such thin layers
  the volume-ratio check warns where the layers meet the much larger triangles: that is true and is
  meant for viscous flow (Phase 4), where the layers will be chosen from the target y+.
- The GUI rebuilds the mesh after every input change only while the estimated mesh is below
  50,000 cells; above that, press **Generate mesh**.
- Files: `cases/external_2d/mesh/mesh.npz` and `mesh.vtu` (ParaView), optionally Gmsh's `mesh.msh`.

## Checks and validation

Mesh quality checks (`aeroflowsim/checks.py`): positive volumes, aspect ratio, non-orthogonality,
neighbour volume ratio (limit 4 with triangles), smallest triangle angle (warning below 20°, error
below 5°), equiangle skewness (warning above 0.85), inflation thickness, smallest cell.

`validation/external_geometry`: cylinder wall length vs π D, domain areas (cylinder, diamond airfoil,
wedge) and the cone's domain volume of revolution vs exact values, on three mesh sizes; tolerance
0.1 %, the error falls as the mesh is refined.
