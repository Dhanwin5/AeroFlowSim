# Tutorial: NACA 0012 on a structured C-grid

You will mesh a NACA 0012 airfoil with a body-fitted grid of quadrilaterals (a *C-grid*: it wraps round the
leading edge and runs back along the wake), look at its quality, and run a subcritical flow on it. About 20 minutes
of computing at the Medium size.

## 1. Start

1. File > New project, template **Body in free stream (2D Euler)**.
2. Geometry step, *Shape*: **NACA 4-digit airfoil**, digits `0012`, chord 1 m, **Closed (sharp) trailing edge** on
   (a C-grid needs a sharp trailing edge; a blunt one gives a message saying so).

## 2. The mesh

3. Mesh step, *Mesh type*: **Structured C/O-grid**. Under the inputs the line *Structured grid* says
   "C-grid (airfoil, with a wake)". For a body that does not fit (a wedge, a diamond airfoil, a body with a flat base) the same
   line says why, and you use the unstructured mesh.
4. *Grid size*: **Medium** (160 cells around the airfoil, 60 normal to the wall, 50 along each wake line = 15,600 cells).
   *Custom* lets you type the three numbers.
5. *First layer height / reference length* `0.002`: the cell touching the wall is exactly 0.002 chords high. The layers
   then grow by a constant ratio that fills the distance to the far field (20 chords) with 60 layers; if that ratio would be
   more than *Largest growth rate* (1.35) the mesh stops and says how many layers you need.
6. Press **Mesh**. Look at the mesh (zoom into the nose and the trailing edge: the cells are small at both edges, the grid
   lines leave the wall at a right angle) and at the quality fields: skewness stays below 0.5 and the smallest angle above 50 degrees
   for this airfoil. The boundaries are named **wall** and **farfield**, exactly as in the unstructured mesh, so everything
   after this step is the same.

## 3. Run

7. Setup: Mach 0.5, angle of attack 1.25 deg, the rest as default. Run.
   Reference (Vassberg and Jameson 2010, their NACA 0012 geometry, grid-converged inviscid): Cl = 0.180.
   What we measured (Medium C-grid, 8,000 iterations, not yet converged): Cl = 0.175, Cd = 0.0008. The unstructured triangle mesh of
   similar size gave Cl = 0.168 and Cd = -0.0001 after the same number of iterations; the structured grid is closer to the reference.

## What to try

- Halve the first layer height: the first cell becomes exactly half as high; the cell count does not change.
- *Coarse* and *Fine*: 3,900 and about 41,600 cells.
- *Half domain* (symmetric airfoil only, angle of attack 0): half the cells, with the symmetry patch on y = 0.
- A cylinder with *Mesh type* Structured gives an **O-grid**: rings of cells round the body, orthogonal to 1e-3 degrees.
