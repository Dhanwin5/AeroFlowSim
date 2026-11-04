# Body in free stream (3D Euler)

A 3D body with its axis along x (the flow direction) inside a far field, meshed with **tetrahedra** and, on the
walls, optional **prism layers** (off by default: Euler runs need none), solved with the 3D Euler solver.

## Flow
- Steady inviscid 3D Euler (5 equations), implicit LU-SGS, Green-Gauss gradients, Venkatakrishnan K = 1 (the 3D
  defaults, see docs/theory_manual.md section 13h); far field (Riemann invariants) round the body, slip walls,
  symmetry planes (half / quarter domain); free stream with angle of attack (towards +y) and sideslip (towards +z).
- Forces and moments of the WHOLE body (mirrored across the symmetry planes): Cd, Cl, Cy, CMx, CMy, CMz, Cm = -CMz;
  reference area / length typed, or 0 = frontal area / body length from the walls (smart rule).
- A mesh with an inlet boundary (a STEP fluid nozzle, faces named inlet / outlet) is an internal flow: total-pressure
  inlet, pressure outlet; mass flow, thrust two ways, Isp, Cf (whole nozzle).
- Mesh only option (Solver group) for meshes meant for another solver.
- Validation: validation/euler3d_cone (Taylor-Maccoll), euler3d_sphere (Billig), euler3d_nozzle (vs 2D axisymmetric).

## Geometry
- Template body: sphere (diameter), cylinder (diameter, length), nose cone (base diameter, length; tip upstream at
  x = 0) or box (side, length). Reference length L = the largest extent of the body.
- Far field: box (upstream, downstream and side distances), cylinder about the x axis (upstream, downstream, radius)
  or sphere (radius), all in multiples of L; optionally only y >= 0 with a symmetry plane at y = 0.
- In the Geometry step the geometry is a 3D workspace history: add bodies, import STEP/IGES solids, combine them
  (union, subtract, intersect), move / rotate / scale / mirror, put an enclosure round them, name the faces
  (patches) and add refinement regions (box, sphere, cylinder). Every step is undoable.

## Mesh (aeroflowsim/workspace_mesh3d.py)
- Cell size on the walls h_wall and largest size h_max (x L), growing away from the walls as
  h(d) = min(h_max, h_wall + (growth - 1) d); curved faces get at least n cells per circle of curvature.
- Prism layers (optional, per wall): first layer height (x L), number of layers, growth rate. They are grown from
  the wall triangles along angle-weighted normals and end cleanly on flat neighbouring boundaries (symmetry plane).
- Tetrahedra fill the rest (Gmsh Delaunay). Quality: skewness (equivolume for tetrahedra), dihedral angle,
  non-orthogonality, volume ratio, aspect ratio; negative volumes are an error.

## Assumptions and limits
- No flow solution yet (solver = false).
- The free-stream inputs are used for the first-layer suggestion (y+ = 1 at the free-stream Reynolds number based
  on L, flat-plate skin friction).
- Prism layers cannot end on a curved boundary that is not a wall (a clear message says so).

## Tests
`test_case.py`: discovery, template geometry, every body meshed with the right fluid volume, prism layers with a
half domain, estimate, derived numbers and the first-layer suggestion. Validation: `validation/mesh_3d/` and
`validation/geometry_3d/`.
