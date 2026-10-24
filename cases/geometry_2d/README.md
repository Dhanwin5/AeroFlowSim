# Custom 2D geometry, 2D Euler (`geometry_2d`)

Your own planar or axisymmetric 2D geometry, made in the **Geometry step** (the geometry
workspace) and meshed with Gmsh. Use it for a nozzle drawn in CAD, an airfoil from a coordinates
file, or any 2D domain that no other template describes.

## Workflow

1. **Geometry step.** Import a file (DXF, STEP, IGES, CSV or Selig/Lednicer `.dat`), or draw one.
   - A file that is already a fluid domain (for example a half nozzle with plenum and plume region,
     with an edge on the axis y = 0) is imported as **fluid**.
   - A closed body (an airfoil) is imported as **solid**; add an **Enclosure** (circle, rectangle or
     C-domain) to make the fluid around it.
   - Switch **Axisymmetric** on for bodies of revolution and nozzles (x = axis, y = radius).
2. **Name every boundary edge** (Boundaries tab): *Accept suggestions*, then select the remaining
   edges and press *Name boundary*. The names become the mesh patches and the rows of the boundary-
   condition table in the Setup step. Mark walls for **inflation layers** if you want them.
3. **Mesh step.** Cell sizes are multiples of the **reference length L** (Dimensions tab of the Geometry step): the length along x of
   the bodies, or of the whole fluid region if there is none.

## Assumptions

- 2D: planar (1 m deep) or axisymmetric about the x axis (y ≥ 0, with an `axis` boundary on y = 0).
- The geometry comes only from the project's workspace history (`geometry/history.json`); this
  template has no geometry inputs of its own.
- **Flow (Setup step):** *Internal* (nozzle, duct): inlets start as total-pressure inlets (p0, T0), outlets
  and far fields as pressure outlets at the back (ambient) pressure, so a nozzle with a plume region works
  as it is; nozzle numbers (mass flow, thrust two ways, Isp, Cf, Cd); quasi-1D start for axisymmetric
  nozzles (from the wall profile of the mesh). *External* (body in a free stream): far fields at the free
  stream; Cl, Cd, Cm with the reference length of the Geometry step (Dimensions) and the reference area
  (0 = automatic: L x 1 m, or pi r_max² for axisymmetric bodies). Solver: `aeroflowsim/euler/`, theory
  manual section 12.
