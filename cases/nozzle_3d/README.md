# 3D nozzle (3D Euler)

A converging-diverging nozzle in 3D: the conical contour of the axisymmetric nozzle template (`cases/nozzle_axi`,
same inputs and defaults: a CubeSat-size N2 nozzle, throat 0.28 mm, area ratio 10.6) revolved about the x axis.

## Geometry and mesh

- **Quarter** (default): a 90-degree revolve with two flat symmetry planes (y = 0 and z = 0); all reported mass flows and
  thrusts are for the whole nozzle (x 4). **Full**: 360 degrees.
- **Plume region** (optional): a cylinder of gas behind the exit, `plume_length` x `plume_radius` exit diameters. It
  is its own cell zone (`plume`), joined to the nozzle zone (`nozzle`) by Fluid zones (Gmsh Fragment): the exit plane
  is a conformal interface (interior faces), not a boundary. Its outer faces (`plume_outlet`) are pressure outlets at
  the back pressure; the annulus around the exit (`plume_base`) is a slip wall (a nozzle flush in a base plate).
- Tetrahedra (+ optional prism layers) from the 3D workspace mesher; sizes are multiples of the throat diameter.
- In the Geometry step the nozzle can be replaced (e.g. a STEP nozzle with faces named inlet / outlet / wall).

## Flow and numbers

Steady 3D Euler (or laminar / RANS) equations with the 3D defaults of `external_3d` (implicit LU-SGS, Green-Gauss with
node values, Venkatakrishnan K = 1, update limit 0.2). Inlet: total pressure and temperature (chamber); outlet: back
pressure (a supersonic exit ignores it). Starts from the quasi-1D solution.

- Mass flow, discharge coefficient (vs the 1D choked mass flow).
- Vacuum thrust two ways: the exit-plane momentum flux `F_vacuum` = int (rho u^2 + p) dA, and the wall thrust
  `F_vacuum_wall` (inlet momentum + pressure on the nozzle wall only, patch `wall`). With a plume region both exit
  numbers are measured on the nozzle -> plume interface, from the solver's own interface fluxes.
- Isp, Cf = F / (p0 A_throat), exit Mach number and pressure.

Assumptions: calorically perfect gas, inviscid unless a viscous flow model is chosen, steady.

## Validation

`validation/nozzle_3d/`: the quarter 3D nozzle against the axisymmetric `nozzle_axi` result on the same contour
(mass flow, vacuum thrust, Isp; tolerance pre-registered in `reference.toml`).
