# Tutorial: a sphere at Mach 3 in 3D

Goal: the bow shock in front of a 0.1 m sphere at Mach 3, its stand-off distance, and the drag coefficient, with the
3D Euler solver. About 15 minutes, most of it the run.

## 1. Project

*File > New project*, template **Body in free stream (3D Euler)**, name `sphere`. (Or open the example
*Sphere at Mach 3 (3D)*: it has exactly the settings below.)

## 2. Geometry

Inputs panel, group *Body*: Body shape **Sphere**, Diameter **100 mm**. Group *Far field*: Domain shape **Box**,
Upstream **2**, Downstream **3**, Lateral **2** (reference lengths; the bow shock and the wake fit inside), tick
**Half domain** and **Quarter domain**. The 3D view shows a quarter of a box with the quarter sphere cut out; the two
cut planes are the boundary *symmetry*.

Why a quarter: the flow around a sphere at zero incidence is symmetric about both planes, so a quarter of the cells
gives the same answer four times faster; forces are reported for the whole sphere.

## 3. Mesh

Mesh step: Cell size on the body **0.04** (L), largest **0.5**, prism layers **off** (inviscid). *Generate mesh*:
tetrahedra, about 15,000 cells. The Validity checks panel shows the mesh checks and *Run memory* (a few MB).

## 4. Setup

Free stream: Mach **3**, p 101.325 kPa, T 288.15 K, angles 0. Reference area and length **0** (automatic: the
frontal area of the whole sphere, 7,854 mm², and 100 mm). Boundary table: *wall* slip wall, *farfield* far field,
*symmetry* symmetry. Numerics: keep the 3D defaults (LU-SGS, Green-Gauss, K = 1, 100 first-order iterations).

## 5. Run

*Run*. The residual plot shows five equations (mass, three momentum, energy) and the Cd monitor. Expect a few thousand
iterations on this coarse mesh. Known limit (gap register): on much finer tetrahedral meshes (60,000+ cells) the
second-order run at Mach 3 does not converge yet; if it diverges, lower the CFL number or use SSP-RK3. Try *Stop*, then *Run* again: it carries on from the same iteration.

## 6. Results

The Key numbers show Cd (about 0.92-0.95 inviscid), the symmetry factor 4 and the frontal area. In the 3D view:
- *Display* **Slice plane**, normal **z**, slider near the bottom: the bow shock in the plane z = 0+;
- *Field* **Pressure coefficient** and *Display* **Walls**: Cp on the sphere (about 1.8 at the nose);
- right-click just in front of the nose to probe the Mach number behind the shock (about 0.47).

Stand-off: Billig's correlation gives Delta / R = 0.143 exp(3.24 / M²) = 0.205, i.e. about 10 mm in front of the
nose. The validation case `validation/euler3d_sphere` measures it automatically.

## 7. Export

*Save .vtu* opens the result in ParaView; the automatic report (*File > Report*) has slices of Mach number and
pressure; `python -m aeroflowsim export sphere.afsproj --format vtu` does the same from the command line.
