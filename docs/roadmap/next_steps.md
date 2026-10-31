# After the 2D alpha (v0.2.0a1): where the next stages fit

The next priority is the path to 3D: **speed -> 3D geometry and meshing -> 3D Euler solver**. A 3D solver is
only usable when runs are fast, so speed comes first; 3D geometry and meshing (STEP, tetrahedra, prism layers) come
before the 3D solver because the solver is already 3D-ready (face-based mesh, flux and gradients tested on 3D cells).

| Prompt | What | Where it fits | Why there |
|---|---|---|---|
| 8 | Numba, implicit LU-SGS, multi-core, residual stalls | next | everything else is easier to use and test when runs take seconds |
| shapes, grids and mesh import | remaining shapes, structured C/O grids, mesh import (Gmsh .msh, SU2, CGNS, Fluent .msh) | between 8 and 9 (one Sonnet session) | mesh import is a step towards 3D meshes from other tools; C/O grids give the best 2D airfoil and blunt-body meshes for the NACA 0012 and cylinder studies |
| 9 | 3D geometry workspace (STEP) + 3D Gmsh meshes (tetrahedra, prism inflation) | after 8 / shapes, grids and mesh import | needs speed for testing on real 3D meshes |
| 10 | 3D Euler, multiple zones | after 9 | the solver core is 3D-ready; needs 3D meshes and speed |
| AI assistant | AI assistant plugin v1 (fills schema inputs only, opt-in, local model) | after 10, or in parallel as a separate Sonnet session | independent of the solver; every new input becomes available to it automatically, so the later it comes the more it can do |
| 8b-8e | low-Mach preconditioning, adaptive refinement, batch runs, unsteady | after 10 (parametric studies batch runs earlier if users ask for polars) | improve breadth; not on the critical path to 3D |

Release plan: v0.2.0a2 after the speed stage; v0.3.0a1 after the 3D Euler solver stage (first 3D). Before the installer is shared
with anyone else, the repository must be public (or the source attached to each release), because Gmsh is GPL.
