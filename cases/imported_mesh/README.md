# Start from an existing mesh

Inviscid 2D / axisymmetric flow on a mesh made in another program.

1. **Mesh file.** Gmsh `.msh` (version 2 or 4, ASCII or binary), SU2 `.su2`, CGNS (unstructured, HDF5) or Fluent `.msh` (ASCII).
   Only triangles and quadrilaterals in 2D. Every boundary of the mesh must have a name.
2. **Unit and type.** Pick the length unit of the coordinates and *Planar* or *Axisymmetric* (axisymmetric: y is the radius).
3. **Boundary types.** Each boundary name becomes a patch with a type (inlet, outlet, wall, axis, farfield, symmetry). Names that say
   what they are need no entry; for the others write `name: type` in *Boundary types*. The numbers under the inputs list every name
   and the type it gets. Wall patches are slip walls by default and carry the forces.
4. Then the usual workflow: mesh checks, the boundary-condition table, free stream, run, results.

The same file code is on the command line: `python -m aeroflowsim mesh-info <file>` and
`python -m aeroflowsim mesh-convert <in> <out>`. A project keeps a copy of the mesh file. Edited geometry in the workspace does not
exist here: change the mesh in the program that made it.
