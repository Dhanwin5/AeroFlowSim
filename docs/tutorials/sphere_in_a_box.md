# Tutorial: a sphere in a box (3D mesh with prism layers)

You will make a 3D mesh around a sphere: tetrahedra in the far field and prism layers on the sphere, check its
quality and export it for another solver. About 10 minutes. (The 3D flow solver comes in the next development
stage; this tutorial ends with a checked mesh.)

1. **New project.** *File > New project…*, template **Body in free stream (3D, mesh only)** (`external_3d`). The
   Geometry step shows the 3D workspace: a sphere (diameter 0.1 m) inside a box far field. Rotate with the left mouse
   button, zoom with the wheel, pan with the middle button; the buttons above the view give the standard views.
2. **Look inside.** Choose *Section* **y** in the tool bar: the near half of the box is cut away and the sphere
   appears. Click the sphere: the Properties panel shows its face id `op1:surface`, its area (31 416 mm², that is
   pi D²) and its boundary `wall (wall)`. Set *Section* back to **off**.
3. **Name the sphere.** With the sphere selected press **Name boundary…**, type the name `sphere`, type *Wall*,
   tick *Prism layers on this wall*, OK. The Boundaries tab lists `sphere` (wall, 1 face, prism layers yes) and
   `farfield` (6 faces). Edit > Undo takes the name back, Redo brings it again.
4. **Change the domain (optional).** In the Inputs panel set *Far-field shape* to *Sphere* and *Radius / L* to 10.
   The geometry is replayed; the name `sphere` stays on the sphere because face ids are stable.
5. **Mesh settings.** In the Mesh inputs: cell size on the body 0.05 L, largest cell size 1 L, cells per circle 24.
   Tick **Prism layers on the body**. Press **Suggestions…** in the Geometry tool bar: the first-layer height for
   y+ = 1 at Mach 2 and sea-level air (Re = 4.7 million on D) is about 0.56 µm (5.6e-6 L); for this tutorial keep a
   visible 5e-4 L with 5 layers.
6. **Generate the mesh.** Mesh step, **Generate mesh**. The summary lists the tetrahedra and prisms, the smallest
   dihedral angle, the first prism layer; the Validity checks panel shows *First layer height* (measured against the
   requested height), *Skewness* (equivolume for tetrahedra), *Dihedral angle* and *Cell volumes* (an error would stop
   any run). A big mesh can be stopped with the ✕ in the Mesh chip of the workflow strip.
7. **Look at the quality.** *Colour by* **Skewness (equivolume for tetrahedra)**, *Cut* **y**: the cells the plane
   passes through are shown, the thin prisms round the sphere and the tetrahedra growing outwards. Move the slider to
   move the cut. The histogram on the right shows the skewness of all cells (logarithmic: the few worst cells are
   visible). **Worst cell** zooms to the most skewed cell and shows its values.
8. **Export.** **Export mesh…**, choose *SU2* (or Gmsh, CGNS, ParaView .vtu). The patches keep their names `sphere`
   and `farfield`. From a command prompt: `python -m aeroflowsim export "<project>.afsproj" --mesh sphere.su2`.
9. **Save and reopen.** File > Save; reopening the project shows the same geometry, names and mesh.

What was checked for you: `validation/mesh_3d/` meshes this geometry (sphere D = 1 m, box 16 x 11 x 11 m, 5 prism
layers from 2 mm) on three levels and compares the fluid volume (to 0.000 %), the wall area and the first-layer height
(0.4 %) with exact values.
