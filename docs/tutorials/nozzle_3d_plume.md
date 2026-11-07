# Tutorial: a 3D nozzle with an exhaust plume region

You will compute the 3D flow through a small cold-gas (N2) CubeSat nozzle and the jet behind it, check the numbers
against the axisymmetric result, and look at the plume. About 20 minutes, most of it computing.

## 1. The nozzle

1. *File > New project…*, template **3D nozzle (3D Euler)** (`nozzle_3d`). The Geometry step shows a quarter of the
   conical nozzle (throat 0.28 mm, exit 0.91 mm): the template's own contour, the same as the axisymmetric nozzle.
   The two flat cut faces are the **symmetry** planes; the faces at the ends are `inlet` and `outlet`, the cone
   surfaces `wall`.
2. In the Inputs panel (Geometry group) tick **Plume region behind the exit**, length 5 and radius 2 exit diameters.
   The view shows a quarter cylinder behind the exit. It is its own **cell zone** `plume`; the nozzle is the zone
   `nozzle`. The old exit plane is now inside the gas (the interface between the zones); the plume's outer faces are
   `plume_outlet` (pressure outlets) and the ring around the exit `plume_base` (a wall: the nozzle sits in a base
   plate).
3. Open the **Boundaries** tab: inlet, wall, symmetry, plume_outlet, plume_base. No boundary is called outlet any more.

## 2. Mesh

1. Mesh inputs: *Cell size on the wall* 0.2 throat diameters (five cells across the throat), *Largest cell size* 1.
   The Estimated cells under the inputs says about 20,000.
2. Go to **Mesh** and press **Generate mesh**. The Messages panel lists the patches and the two zones.
3. Optional, sharper plume: in the Geometry step turn on the **Edges** filter, click the circular edge of the nozzle lip,
   *Edit > Edge size…* 0.05 mm. Mesh again.

## 3. Setup and run

1. **Setup**: the boundary table has the inlet (total pressure 5 bar, 293.15 K: the chamber), the plume outlets
   (pressure outlet, 1 kPa) and the walls (slip). The Numerics keep the 3D defaults.
2. **Run**. The monitors show thrust and mass flow; the run stops when the residual has dropped six orders and the
   monitors have settled. *Stop* ends the run cleanly; *Run* again continues from where it stopped.

## 4. Results

1. **Key numbers** (for the whole nozzle, x 4): mass flow about 0.070 g/s (compare *mdot_1D*), vacuum thrust about
   0.049 N two ways (exit plane = the zone interface, and the wall pressure), Isp about 71 s.
2. **View** tab: *Display* Slice plane, normal z, slider near the middle: the jet's Mach number. Field *Cell zone*
   shows the two zones.
3. **XY plot** tab: field Mach number, plane normal z, position 0.00001 m, plot against x, tick `wall` in Patches:
   the Mach number along the nozzle wall.
4. **Reports** tab: *Evaluate*: the flux balance per zone; the mass flow from the nozzle into the plume equals the
   inlet mass flow at a steady state.
5. Compare with the axisymmetric nozzle: open a `nozzle_axi` project with the same inputs. The validation case
   `validation/nozzle_3d` does this (mass flow within 3 %, Isp within 0.5 % on the default meshes).

## What to try next

- Untick the plume region: the exit plane is the outlet again; the thrust is the same (the exit is supersonic).
- Laminar flow: *Flow model* Laminar and *Prism layers on the body* in the Mesh inputs (validation/nozzle_3d_laminar).
- Your own nozzle: in the Geometry step delete the template body, *Import…* a STEP nozzle (fluid, faces named inlet,
  outlet, wall; see `nozzle_step_to_mesh.md`) and add **Plume / plenum…**.
