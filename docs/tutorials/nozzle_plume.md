# Tutorial: a nozzle with an exhaust plume region

You will mesh the inside of a small cold-gas nozzle **and** the region behind it where the jet
expands, with boundaries named for the 2D axisymmetric solver (Prompt 7). Two ways: from the
built-in nozzle template (A), or from your own CAD drawing (B). About 10 minutes.

## A. From the nozzle template

1. **New project.** *File > New project…*, template **Axisymmetric nozzle - mesh**
   (`nozzle_axi`). The Geometry step shows the conical nozzle; its inputs (throat diameter, angles,
   exit diameter) are in the Inputs panel on the left, as before.
2. **Add the plume region.** Press **Enclosure…** in the geometry tool bar. Because there is no body
   (the fluid is the inside of the nozzle), the dialog proposes **Nozzle: plume region**. Type the
   size in exit diameters, for example length 10 and height 5, and press OK.
   - The box is joined to the nozzle: the old exit plane is now inside the fluid.
   - Its right side is named `outlet`, its top `farfield`, and the step at the nozzle lip is part
     of `wall`.
3. **Optional: an inlet plenum.** *Enclosure…* again, choose **Nozzle: inlet plenum** (length and
   height in inlet diameters). Its left side becomes the `inlet`.
4. **Check the boundaries.** Open the **Boundaries** tab: inlet, outlet, wall, axis and farfield.
   Click a row to see its edges highlighted in yellow. To rename a boundary (e.g. `farfield` →
   `ambient`), select its row and press *Rename…*.
5. **Resize by dragging (optional).** Choose **Drag points**, click the plume step in the History
   tab, and drag the red handle at the outer corner of the box. Or type exact numbers in the History
   tab and press *Apply*.
6. **Refine the shear layer.** Press **Refinement…**, choose *box*, and type a region from the exit
   lip downstream (lengths in mm) with a small cell size. It appears in orange.
7. **Mesh.** In the Mesh inputs choose **Mesh type: Triangles (Gmsh)**. The structured mesh only
   follows the template's own nozzle, so an edited geometry needs Gmsh; you will get a message if
   you forget. Then go to the Mesh step and press **Generate mesh**. The patch list shows your
   boundary names.
8. **Suggestions.** Press **Suggestions…** for recommended wall and largest cell sizes, each with
   its reason. Nothing changes until you press *Apply* (and Edit > Undo takes it back).

## B. From your own CAD file (DXF, STEP or IGES)

1. **New project** from the template **Custom 2D geometry - mesh** (`geometry_2d`). It starts empty.
2. **Import.** Press **Import…** and choose the file. In the dialog:
   - **Unit of the numbers**: *As the file says* (STEP, IGES and most DXF files state their unit),
     or mm / m / inch if the preview sizes look wrong.
   - **The faces are**: *Decide* imports a face that has an edge on y = 0 as **fluid** (a half
     nozzle domain).
   - The preview lists the size, the faces and their areas, and what the healing fixed (joined gaps,
     removed duplicates). These notes also appear in the Messages panel.
3. Switch **Axisymmetric** on (tool bar): x is the axis, y the radius.
4. **Name the boundaries.** In the Boundaries tab press **Accept suggestions**. The edge on y = 0
   becomes `axis`; the edges across the flow at the far left and far right become `inlet` and
   `outlet`. Then click the remaining edges (Shift-click for several), press **Name boundary…**,
   and give them a name and a type: `nozzle_wall` / wall, `ambient` / far field.
5. If your drawing is only the nozzle, add the plume region as in A.2. If it already contains the
   plume box (like a typical CFD-domain drawing), skip that.
6. **Mesh step → Generate mesh.** The cell sizes are multiples of the reference length L (the length
   of the fluid region along x, shown in the Dimensions tab). The Validity checks panel shows the
   geometry checks (every edge named, y ≥ 0, axis present, smallest feature against the wall cell
   size) and the mesh checks.

**Save** keeps the whole history in `geometry/history.json`. Your imported file is copied into the
project, so a zipped project reproduces the same geometry and mesh.
