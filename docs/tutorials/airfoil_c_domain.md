# Tutorial: an airfoil in a C-domain

The C-domain is the standard domain for airfoils: a half circle upstream and a rectangle
downstream, so the wake leaves through a straight boundary. You will mesh a NACA 0012 at an angle
of attack, with a refined wake. About 10 minutes.

1. **New project** from the template **Body in free stream - mesh** (`external_2d`). In the Inputs
   panel choose **Shape: NACA 4-digit airfoil**, digits `0012`, chord 1 m.
2. **Switch off the template's far field.** In the **History** tab, click
   *op2 Template far field* and press **Suppress**. The airfoil now stands alone as a solid body
   (grey).
3. **Angle of attack.** Click the airfoil to select it, then **Edit ▾ > Transform…**:
   - **Rotate**, angle `-4` (a negative angle lifts the nose), centre x = 250 mm, y = 0
     (the quarter chord), OK.
   - The History tab shows the step. Click it later to change the angle; everything after it is
     rebuilt.
4. **The C-domain.** Press **Enclosure…**, choose **C-domain (airfoils)**, radius `20` and
   downstream `20` (in chords L), OK.
   - The airfoil is cut out of the domain.
   - Its edges are named `wall` and the outer boundary `farfield`; the Boundaries tab lists both.
   - For a half domain (a symmetric airfoil at zero angle) tick *Half domain*; the line y = 0 then
     becomes `symmetry`.
5. **Refine the wake.** Press **Refinement…**, choose **wake**, start at the trailing edge
   (after the rotation about x = 998 mm, y = -52 mm; the trailing edge moves down when the nose goes up),
   end 5000 mm downstream, width 200 mm, cell size 10 mm.
   - With **Drag points** you can drag its two ends.
   - Add a **box** or **circle** around the leading edge the same way if you like.
6. **Suggested sizes.** Press **Suggestions…**:
   - wall cell size at most L/100, and at least 4 cells along the smallest wall feature;
   - largest cell size about 2 L;
   - corner refinement on (the trailing edge is a sharp corner);
   - a check that the far field is at least 20 L away (subsonic).

   Apply the ones you want.
7. **Mesh step → Generate mesh.** The patches are `wall` and `farfield`, the names from the
   Boundaries tab. Click a cell to see its quality; the Validity checks panel lists the geometry and
   mesh checks.
8. **Export** (optional): **More ▾ > Export geometry…** saves the geometry as STEP (exact CAD),
   DXF (mm, one layer per boundary) or CSV points.

**Tips**

- *Edit > Undo* (Ctrl+Z) undoes every workspace step, one at a time.
- **Inflation layers:** select the airfoil edges, *Name boundary…* with *Inflation layers on these
  edges*, and switch inflation on in the Mesh inputs.
- **Your own airfoil coordinates:** **Import…** a Selig or Lednicer `.dat` file. It comes in as a
  solid body (unit: metres unless you choose otherwise); continue from step 3.
