# Axisymmetric nozzle, 2D mesh (`nozzle_axi`)

A 2D **axisymmetric** mesh of a converging-diverging nozzle: the upper half of the meridional
plane, from the axis (r = 0) to the wall, from the inlet to the exit. The default geometry is the
same N2 cold-gas thruster as the quasi-1D case (inlet Ø 2.0 mm, straight inlet 1.33 mm, 30°
convergent cone, throat Ø 0.280 mm, 15° divergent cone, exit Ø 0.911 mm, A_e/A* = 10.59).

**Status:** mesh only (`solver = false` in `schema.toml`). The 2D axisymmetric Euler solver
arrives in Prompt 7 and will use this mesh unchanged. The GUI's Run tab says so; the Results tab
shows the mesh quality checks.

## Geometry

Level 1 (parametric conical nozzle) or Level 2 (wall profile CSV, header `x_mm,r_mm`), both read
by the shared `aeroflowsim/geometry.py`. The example CSV in `examples/` is the default nozzle.

**Rounded throat** (parametric nozzle): `Rcu/Rt` and `Rcd/Rt` are the wall's radii of curvature just
upstream and downstream of the throat, divided by the throat radius (default 0 = sharp throat;
typical 1.5 and 0.4). Each arc is tangent to its cone, both arcs are horizontal at the throat, the
throat and exit diameters stay exact and the cones get shorter. An arc that does not fit gives an
error with the largest ratio that fits. The preview marks the tangent points.

## Mesh type

- **Structured** (default): quads, described below.
- **Triangles (Gmsh)**, needs `pip install -e ".[mesh]"`: unstructured triangles or quad-dominant
  cells from `aeroflowsim/gmsh_mesh.py`, with the same patches `inlet`, `outlet`, `wall`, `axis`.
  Sizes are fractions of the throat diameter D_t (wall cell size 0.04 D_t, largest cell 0.2 D_t,
  growth 1.2), with 4 times smaller cells at the throat and at sharp corners. Inflation layers (same
  inputs as for the structured mesh, height measured normal to the wall) are grown from the wall
  by `aeroflowsim/inflation_layers.py`. Both mesh types give the same area and volume to 0.1 %.

## Structured mesh (`aeroflowsim/nozzle_mesh.py`)

- Structured quad cells. "Vertical" grid lines at `nx + 1` axial stations from the axis to the wall;
  "horizontal" grid lines following the wall shape. Patches: `inlet`, `outlet`, `wall`, `axis`.
- The wall between two stations is a straight line. The throat is always exactly a station; other
  corners of the profile (e.g. the end of the straight inlet) can fall between two stations and are
  then cut slightly. This error falls as the mesh is refined (see the validation below).
- **Presets:** Coarse 100 × 20, Medium 200 × 40, Fine 400 × 80 cells, or Custom.
- **Throat clustering:** each side of the throat gets cells in proportion to its length, spaced
  with a smooth one-sided tanh stretching `s = 1 + tanh(δ(ξ − 1)) / tanh δ`, finest at the throat.
  Throat cells are about `2δ / sinh 2δ` times the uniform size: Mild δ = 1 (0.55), Moderate δ = 2
  (0.15), Strong δ = 3 (0.03).
- **Inflation layers** (off by default; for viscous flow later): first layer height `h`, `n`
  layers, growth rate `g`; total thickness `h (gⁿ − 1)/(g − 1)` (shown read-only in the Setup tab).
  Heights are measured radially, along the vertical grid lines, so the layers stay smooth at the
  sharp throat corner. On a wall at angle α the wall-normal first-cell height is `h cos α`
  (0.97 h on the 15° cone, 0.87 h on the 30° cone): slightly smaller than asked, the safe side
  for y+. The cells between the layers and the axis start at `g ×` the last layer (no size jump);
  where there is little room (narrow throat, many cells across) they shrink back to a constant size
  instead of becoming tiny at the axis.
- The mesh is the face-based `Mesh` of `aeroflowsim/mesh.py` (axisymmetric flag on): per-radian
  metrics `area × r` and `volume × r` are stored next to the planar values.

## Files

Generating the mesh in the GUI writes `cases/nozzle_axi/mesh/mesh.npz` (reload with
`Mesh.load`) and `mesh.vtu` (ParaView: cell volume, aspect ratio, non-orthogonality, volume
ratio, cell size, patch marker). This folder is git-ignored.

## Checks and validation

- Mesh quality checks (`aeroflowsim/checks.py`): positive cell volumes (error otherwise; the solver
  then refuses to run), aspect ratio (warning above 100, info only with inflation),
  non-orthogonality (warning above 70°), neighbour volume ratio (warning above 2; 4 with
  triangles), smallest triangle angle (triangle meshes: warning below 20°, error below 5°),
  equiangle skewness (warning above 0.85), inflation thickness (warning above 50 % of the throat
  radius), smallest cell (info).
- `validation/external_geometry`: the volume of the rounded-throat nozzle (Rcu/Rt = 1.5,
  Rcd/Rt = 0.4) against the exact volume (cylinder, frustums and arc sections in closed form), for
  the structured and the triangle mesh.
- `validation/nozzle_axi_geometry`: mesh area, volume of revolution and wall length against the
  exact values for the default nozzle, on Coarse, Medium and Fine meshes (tolerance 0.1 % on
  Medium). The non-orthogonality of about 30° comes from the 30° convergent wall: vertical
  grid lines meet the sloping horizontal lines at the wall angle.
