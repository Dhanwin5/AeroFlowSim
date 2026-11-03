# Tutorial: from a nozzle STEP file to a 3D mesh

You will import a nozzle from a CAD file (STEP), name its inlet, outlet and wall, and make a 3D mesh of the gas inside
it with prism layers on the wall that end cleanly on the inlet and outlet planes. About 10 minutes.

The example file `cases/external_3d/examples/conical_nozzle.step` is the gas volume of AeroFlowSim's default N2
cold-gas nozzle (inlet diameter 2 mm, throat 0.28 mm, exit 0.913 mm, 4 mm long), as a CAD program would export it: a
solid of revolution about the x axis, in metres. It was made with AeroFlowSim itself (a Revolve of the conical profile,
then STEP export). Your own file works the same way, in any unit the file states.

1. **New project.** *File > New project…*, template **Body in free stream (3D, mesh only)**.
2. **Import.** In the Geometry step press **Import…** and choose the STEP file. In the dialog set *The solids are*:
   **Fluid (meshed)** (the solid in the file is the gas, not a body in a flow). OK. The import replaces the template's
   body and far field (they stay in the History, suppressed); the nozzle appears, grey: its faces have no names yet.
3. **Name the boundaries.** Boundaries tab, **Accept suggestions**: the flat face across the flow at the smallest x
   becomes `inlet`, the one at the largest x `outlet`, the cones and the cylinder `wall` (with the prism-layer tick on).
   Check by clicking the rows: the faces light up in the view. A different name? Select the row, *Rename…*.
4. **Mesh settings.** The sizes are multiples of the reference length L (here the 4 mm length of the walls): cell
   size on the body 0.06 L, largest cell size 0.12 L, **cells per circle 36** (the throat is only 0.28 mm across:
   36 cells round it keep the faceting error of the area below 0.5 %). Tick **Prism layers on the body**: first
   layer 0.002 L (8 µm), 3 layers, growth 1.2.
5. **Generate the mesh.** Mesh step, **Generate mesh** (a few seconds). With *Cut* **y** you see the prisms along the
   wall and the tetrahedra in the core; at the inlet and outlet the layers end exactly on the planes (their side faces
   are quads on the inlet and outlet patches). The checks list the first-layer height reached and the skewness.
6. **Export** the mesh (**Export mesh…**: Gmsh, SU2, CGNS, .vtu) for another solver, or keep the project for the 3D
   Euler solver (next stage).

Notes
- A STEP file with only surfaces (a closed shell, no solid) is sewn into a solid; open surfaces are refused with a
  message.
- Prism layers can end only on flat boundaries (inlet, outlet, symmetry planes). A curved boundary next to a wall with
  layers is refused with a message: name it a wall too, or switch the layers off on that wall.
- The same steps work with the nozzle wall CSV of the 2D templates: *Bodies > Revolve…*, profile *Nozzle wall file*.

This tutorial is a test: `cases/external_3d/test_case.py::test_nozzle_step_tutorial` (fluid volume 6.343 mm³ read
back from the file, the three names, tetrahedra + prisms, mesh volume within 1 %).
