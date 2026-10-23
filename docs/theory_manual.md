# AeroFlowSim theory manual

This manual explains the equations and numerical methods inside AeroFlowSim, at the level of a
final-year aerospace engineering student. Every section ends with **In the code**: where the
equations live, so you can read the two side by side. SI units throughout.

Contents

1. [Governing equations: the Euler equations](#1-governing-equations-the-euler-equations)
2. [The finite volume method](#2-the-finite-volume-method)
3. [The HLLC approximate Riemann solver](#3-the-hllc-approximate-riemann-solver)
4. [MUSCL reconstruction with the minmod limiter](#4-muscl-reconstruction-with-the-minmod-limiter)
5. [Time integration: SSP-RK2, CFL and local time stepping](#5-time-integration-ssp-rk2-cfl-and-local-time-stepping)
6. [Quasi-1D nozzle flow](#6-quasi-1d-nozzle-flow)
7. [The face-based mesh](#7-the-face-based-mesh)
8. [Mesh generation: structured nozzle, Gmsh, inflation layers](#8-mesh-generation-structured-nozzle-gmsh-inflation-layers)
9. [Geometry: rounded throat and the shape library](#9-geometry-rounded-throat-and-the-shape-library)
10. [Reproducibility: projects, fingerprints and background runs](#10-reproducibility-projects-fingerprints-and-background-runs)
11. [Gas models](#11-gas-models)
12. [References](#12-references)

---

## 1. Governing equations: the Euler equations

For an inviscid, non-heat-conducting ideal gas, conservation of mass, momentum and energy in a
fixed control volume $V$ with surface $S$ and outward unit normal $\mathbf{n}$ reads

$$
\frac{d}{dt}\int_V \mathbf{U}\,dV + \oint_S \mathbf{F}(\mathbf{U})\cdot\mathbf{n}\,dS = 0 ,
$$

with the conserved variables and the flux normal to the surface

$$
\mathbf{U} = \begin{pmatrix}\rho\\ \rho\mathbf{u}\\ E\end{pmatrix},\qquad
\mathbf{F}\cdot\mathbf{n} = \begin{pmatrix}\rho u_n\\ \rho\mathbf{u}\,u_n + p\,\mathbf{n}\\ (E+p)\,u_n\end{pmatrix},\qquad
u_n = \mathbf{u}\cdot\mathbf{n}.
$$

$E$ is the total energy per unit volume, and the ideal-gas equation of state closes the system:

$$
E = \frac{p}{\gamma-1} + \tfrac12\rho|\mathbf{u}|^2,\qquad p = \rho R T,\qquad c = \sqrt{\gamma p/\rho}.
$$

In 1D ($\mathbf{u} = u$, $\mathbf{n} = \pm 1$) this becomes $\partial_t \mathbf{U} + \partial_x \mathbf{F} = 0$ with
$\mathbf{U} = [\rho, \rho u, E]$ and $\mathbf{F} = [\rho u, \rho u^2 + p, u(E+p)]$.

The **integral form** above is the one AeroFlowSim discretises. It remains valid across shocks,
where the differential form does not, which is why finite volume methods capture shocks correctly.

**In the code:** `aeroflowsim/euler1d.py` (`euler_flux`, `primitive_to_conserved`,
`conserved_to_primitive`, `sound_speed`).

---

## 2. The finite volume method

Split the domain into cells $i$ of volume $V_i$. Define the **cell average**
$\mathbf{U}_i = \frac{1}{V_i}\int_{V_i}\mathbf{U}\,dV$. The surface of each cell is made of flat
**faces** $f$ with area $A_f$ and unit normal $\mathbf{n}_f$. Applying the integral law to one cell,
and approximating the flux as constant over each face, gives the **semi-discrete** equation

$$
V_i\frac{d\mathbf{U}_i}{dt} = -\sum_{f\in\text{faces}(i)} \hat{\mathbf{F}}_f\,A_f \;\; (\pm 1),
$$

where $\hat{\mathbf{F}}_f$ is the **numerical flux** through face $f$ in the direction of its normal,
and the sign is $+$ when the normal points out of cell $i$ (cell $i$ is the face's *owner*) and $-$
when it points in (cell $i$ is the *neighbour*).

The key property: **each face flux is added to one cell and subtracted from the other**. What leaves
one cell enters its neighbour exactly, so mass, momentum and energy are conserved to round-off,
whatever the mesh. This is why a solver can loop over faces:

```
for every face f:
    F = numerical_flux(left state, right state, normal of f)
    residual[owner(f)]     -= F * A_f
    residual[neighbour(f)] += F * A_f     (interior faces only)
```

The same loop works in 1D, 2D, axisymmetric and 3D; only the face areas and volumes change
(Section 7). Boundary faces have only an owner; the boundary condition provides the outside state.

**Accuracy.** With constant states in each cell the method is first-order accurate in space. Section
4 makes it second-order by reconstructing linear profiles inside each cell.

**In the code:** 1D: `flux_divergence` in `aeroflowsim/euler1d.py`, $-(F_{i+1/2} - F_{i-1/2})/\Delta x$.
Quasi-1D: `quasi1d_rhs` in `aeroflowsim/quasi1d.py`. The face-based form for 2D/3D arrives with the
2D solver (Prompt 7) on the mesh of Section 7.

---

## 3. The HLLC approximate Riemann solver

At a face we know a **left** state $\mathbf{W}_L$ and a **right** state $\mathbf{W}_R$ (primitive variables
$\mathbf{W} = [\rho, u, p]$). Their jump is a *Riemann problem*: it breaks up into waves. The exact
solution (Toro 2009, ch. 4; `aeroflowsim/riemann_exact.py`) needs iteration, so CFD codes use an
approximate solver. **HLLC** (Harten-Lax-van Leer-Contact; Toro, Spruce & Speares 1994) models the wave
fan with three waves: the fastest left wave $S_L$, the contact $S_*$ and the fastest right wave $S_R$,
with two constant "star" states between them. Unlike HLL it keeps the contact wave, so contact
discontinuities and shear layers stay sharp.

**Wave speeds** (Davis estimate, Toro eq. 10.48):

$$ S_L = \min(u_L - c_L,\; u_R - c_R),\qquad S_R = \max(u_L + c_L,\; u_R + c_R). $$

**Contact speed**, from equal star pressures on both sides (Toro eq. 10.37):

$$ S_* = \frac{p_R - p_L + \rho_L u_L (S_L - u_L) - \rho_R u_R (S_R - u_R)}{\rho_L (S_L - u_L) - \rho_R (S_R - u_R)}. $$

**Star states** ($K = L$ or $R$, Toro eq. 10.39):

$$
\mathbf{U}_{*K} = \rho_K\frac{S_K - u_K}{S_K - S_*}
\begin{pmatrix} 1\\ S_*\\ \dfrac{E_K}{\rho_K} + (S_* - u_K)\left(S_* + \dfrac{p_K}{\rho_K (S_K - u_K)}\right)\end{pmatrix}.
$$

**Flux**: pick the region of the wave fan that contains the face ($x/t = 0$):

$$
\hat{\mathbf{F}} = \begin{cases}
\mathbf{F}_L & 0 \le S_L\\
\mathbf{F}_L + S_L(\mathbf{U}_{*L} - \mathbf{U}_L) & S_L \le 0 \le S_*\\
\mathbf{F}_R + S_R(\mathbf{U}_{*R} - \mathbf{U}_R) & S_* \le 0 \le S_R\\
\mathbf{F}_R & S_R \le 0.
\end{cases}
$$

In 2D/3D the same formulas are applied to the velocity component normal to the face (rotated
frame); the tangential velocity is carried across the contact. Known weakness in 2D: the
"carbuncle" instability of strong bow shocks aligned with the mesh, which Prompt 7 fixes.

**In the code:** `hllc_flux` in `aeroflowsim/euler1d.py`.

---

## 4. MUSCL reconstruction with the minmod limiter

First-order schemes smear shocks and contacts over many cells. **MUSCL** (van Leer 1979) gives
second-order accuracy by assuming a *linear* profile inside each cell and evaluating it at the faces:

$$ \mathbf{W}_{i+1/2}^{L} = \mathbf{W}_i + \tfrac12\boldsymbol{\sigma}_i,\qquad
   \mathbf{W}_{i-1/2}^{R} = \mathbf{W}_i - \tfrac12\boldsymbol{\sigma}_i , $$

where $\boldsymbol{\sigma}_i$ is the change across the cell (slope × cell width). A plain central slope
would create new maxima and minima (oscillations) next to shocks. A **limiter** prevents this by
choosing the slope from the one-sided differences
$\Delta_- = \mathbf{W}_i - \mathbf{W}_{i-1}$ and $\Delta_+ = \mathbf{W}_{i+1} - \mathbf{W}_i$.
The **minmod** limiter takes the smaller one if both have the same sign, and zero otherwise:

$$ \sigma = \operatorname{minmod}(\Delta_-, \Delta_+) =
\begin{cases} \operatorname{sign}(\Delta_-)\min(|\Delta_-|, |\Delta_+|) & \Delta_-\Delta_+ > 0\\ 0 & \text{otherwise.}\end{cases} $$

So the scheme is second-order in smooth regions and drops to first order at extrema and shocks (it is
TVD: total variation diminishing, no new oscillations). Minmod is the most dissipative TVD limiter,
chosen for robustness. The primitive variables are reconstructed, which keeps density and pressure
positive more reliably than reconstructing the conserved ones.

On unstructured meshes (Prompt 7) the slope becomes a cell gradient (least squares or Green-Gauss)
and the limiter a multidimensional one (e.g. Barth-Jespersen or Venkatakrishnan).

**In the code:** `minmod` and `muscl_reconstruct` in `aeroflowsim/euler1d.py` (two ghost cells per side
are needed to reconstruct the boundary faces).

---

## 5. Time integration: SSP-RK2, CFL and local time stepping

Writing the semi-discrete equations as $d\mathbf{U}/dt = \mathbf{L}(\mathbf{U})$, AeroFlowSim uses the
two-stage **strong-stability-preserving Runge-Kutta** method (SSP-RK2, Heun; Gottlieb & Shu 1998):

$$ \mathbf{U}^{(1)} = \mathbf{U}^n + \Delta t\,\mathbf{L}(\mathbf{U}^n),\qquad
   \mathbf{U}^{n+1} = \tfrac12\mathbf{U}^n + \tfrac12\left(\mathbf{U}^{(1)} + \Delta t\,\mathbf{L}(\mathbf{U}^{(1)})\right). $$

It is second-order in time and keeps the TVD property of the spatial scheme.

**CFL condition.** An explicit scheme is stable only if information travels at most about one cell
per step: $\Delta t = \text{CFL}\;\Delta x / \max(|u| + c)$ with CFL below 1.

**Local time stepping (steady cases).** When only the steady state matters, every cell may use its
own largest stable step $\Delta t_i = \text{CFL}\,\Delta x_i/(|u_i| + c_i)$. The intermediate states are
then not physical in time, but the converged steady state is the same (it does not depend on
$\Delta t$), and small cells (e.g. at a throat) no longer slow the whole computation. Convergence is
measured by the **residual**, the RMS of $d\rho/dt$ normalised by its first value; the validity check
requires a drop of at least 6 orders of magnitude.

**In the code:** `ssp_rk2_step`, `cfl_time_step` in `aeroflowsim/euler1d.py`; `local_time_steps` in
`aeroflowsim/quasi1d.py`; the convergence check in `aeroflowsim/checks.py`.

---

## 6. Quasi-1D nozzle flow

For a duct whose area $A(x)$ varies slowly, the flow is assumed uniform over each cross-section.
Applying the integral law to a slice of the duct between $x$ and $x + dx$ gives

$$ \frac{\partial (\mathbf{U}A)}{\partial t} + \frac{\partial (\mathbf{F}A)}{\partial x} = \mathbf{S},\qquad
   \mathbf{S} = \begin{pmatrix}0\\ p\,dA/dx\\ 0\end{pmatrix}, $$

where the source term is the axial force of the slanted wall on the gas. The finite volume form
for cell $i$ between faces $i \pm 1/2$:

$$ V_i \frac{d\mathbf{U}_i}{dt} = -(\mathbf{F}A)_{i+1/2} + (\mathbf{F}A)_{i-1/2} + \begin{pmatrix}0\\ p_i (A_{i+1/2} - A_{i-1/2})\\ 0\end{pmatrix}. $$

This form is **well balanced**: for gas at rest every face flux is $(0, p, 0)$, and the momentum terms
cancel exactly, so no spurious flow is created.

**Boundary conditions.** Inlet (subsonic, from a reservoir): total pressure $p_0$ and total
temperature $T_0$ imposed, the velocity taken from the first cell, then
$T = T_0 - u^2/(2c_p)$, $p = p_0 (T/T_0)^{\gamma/(\gamma-1)}$. Outlet: supersonic → everything
extrapolated; subsonic → back pressure imposed.

**Theory used for validation** (Anderson, *Modern Compressible Flow*, ch. 5):

$$ \frac{A}{A^*} = \frac{1}{M}\left[\frac{2}{\gamma+1}\left(1 + \frac{\gamma-1}{2}M^2\right)\right]^{\frac{\gamma+1}{2(\gamma-1)}},\qquad
   \dot m = \frac{p_0 A^*}{\sqrt{R T_0}}\sqrt{\gamma}\left(\frac{2}{\gamma+1}\right)^{\frac{\gamma+1}{2(\gamma-1)}}, $$

plus the normal-shock relations when the back pressure puts a shock inside the divergent part. The
vacuum thrust is $F = \dot m u_e + p_e A_e$.

**In the code:** `aeroflowsim/quasi1d.py` (`quasi1d_rhs`, `nozzle_boundary`, `inlet_state`),
`aeroflowsim/gasdynamics.py` (isentropic and normal-shock relations),
`cases/quasi1d_nozzle/case.py` (mesh, solver loop, theory, key numbers).

---

## 7. The face-based mesh

Every 2D, axisymmetric and 3D mesh in AeroFlowSim is one `Mesh` object (OpenFOAM-style):

| Item | Meaning |
|---|---|
| nodes | corner points $(x, y, z)$; 2D meshes lie in $z = 0$ |
| cells | node lists in VTK order: triangle, quad (2D); tetrahedron, hexahedron, prism, pyramid (3D) |
| faces | every face once; in 2D an edge swept 1 m in $z$ |
| owner / neighbour | the two cells of a face; the normal points from owner to neighbour; boundary faces have no neighbour and their normal points out of the domain |
| patches | named groups of boundary faces with a type: inlet, outlet, wall, axis, farfield, symmetry |

Faces are ordered: interior faces first, then the boundary faces patch by patch.

**Face geometry.** 2D edge from $\mathbf{a}$ to $\mathbf{b}$: area vector
$\mathbf{S}_f = (\mathbf{b} - \mathbf{a}) \times \hat{\mathbf{z}}\cdot 1\,\text{m}$. 3D polygon: split into triangles
around its mean point; $\mathbf{S}_f$ is the sum of the triangle area vectors, the face centre their
area-weighted centroid.

**Cell volume and centroid.** Split the cell into one pyramid (2D: triangle) per face, with the apex at
the mean of the cell's nodes $\mathbf{x}_c$. A pyramid on face $f$ has volume
$\frac{1}{d}\,\mathbf{S}_f\cdot(\mathbf{x}_f - \mathbf{x}_c)$ ($d$ = 2 or 3) and centroid
$\mathbf{x}_c + \frac{d}{d+1}(\mathbf{x}_f - \mathbf{x}_c)$. Summing over the faces gives the cell volume
(2D: area × 1 m) and centroid, by the divergence theorem. A cell with its nodes in the wrong order
gets a negative volume, which the mesh check reports as an error.

**Axisymmetric metrics.** In the meridional plane $(x, r)$ a cell revolved by one radian sweeps the
volume $A_{cell}\,r_c$ (**theorem of Pappus**, exact for straight-edged cells), and a face sweeps the
area $L_f\,r_f$. These "per radian" values are stored next to the planar ones; the axisymmetric
solver (Prompt 7) uses them, so the same face loop handles axisymmetric flow.

**Quality metrics** (per cell, used by the validity checks):

| Metric | Definition | Check |
|---|---|---|
| aspect ratio | largest / smallest face area | warning > 100 (info inside inflation layers) |
| non-orthogonality | angle between $\mathbf{n}_f$ and the owner→neighbour line | warning > 70° |
| neighbour volume ratio | larger / smaller volume of two neighbours | warning > 2 (quads), > 4 (meshes with triangles) |
| smallest angle | smallest corner angle (triangles) | warning < 20°, error < 5° |
| equiangle skewness | $\max\left(\frac{\theta_{max} - \theta_e}{180° - \theta_e}, \frac{\theta_e - \theta_{min}}{\theta_e}\right)$, $\theta_e$ = 60° (triangle), 90° (quad) | warning > 0.85 |
| cell size | volume / largest face area | info |

Why the volume-ratio limit is larger with triangles: two triangles of the same size but different
shapes already differ about 2.5 times in area, so a limit of 2 would flag every good triangle mesh.

**In the code:** `aeroflowsim/mesh.py` (`Mesh`, `Mesh.from_cells`, `_find_faces`, `_face_geometry`,
`_cell_geometry`), `aeroflowsim/mesh_quality.py`, `aeroflowsim/checks.py`, `aeroflowsim/vtk.py`
(ParaView export).

---

## 8. Mesh generation: structured nozzle, Gmsh, inflation layers

### 8.1 Structured axisymmetric nozzle mesh

Quads on $n_x + 1$ axial stations, from the axis to the wall, with one station exactly at the
throat. Throat clustering uses the one-sided tanh stretching
$s(\xi) = 1 + \tanh(\delta(\xi - 1))/\tanh\delta$, finest at the throat. Optional inflation layers:
first height $h$, growth $g$, heights $h g^{k}$, total $h(g^n - 1)/(g - 1)$; the core cells grow
smoothly from the last layer to the axis. **In the code:** `aeroflowsim/nozzle_mesh.py`.

### 8.2 Unstructured meshes with Gmsh (optional)

[Gmsh](https://gmsh.info) (Geuzaine & Remacle 2009) is used through its Python interface:

1. **Geometry.** The outline is cut at its sharp corners; each piece becomes a straight line (two
   points) or an interpolating spline through its points, so corners stay sharp and curves smooth.
   Far-field circles are exact circle arcs, split into at least 120 faces so the circle stays round.
   Every boundary curve is put in a *physical group* named after its patch.
2. **Size field.** The wanted cell size grows linearly with the distance $d$ from the wall:
   $h(d) = \min(h_{max},\, h_s + (g - 1)\,d)$, so a cell of size $h$ has neighbours of about $g h$
   further out. Corners, leading/trailing edges and the nozzle throat use the same rule from
   $h_s/4$ (edge refinement). In Gmsh: Distance → Threshold fields, combined with a Min field.
3. **Meshing.** Frontal-Delaunay triangulation; for a quad-dominant mesh the triangles are paired into
   quads by the Blossom recombination algorithm.
4. **Conversion to `Mesh`.** Gmsh node tags are renumbered $0 \dots N-1$; triangles (Gmsh type 2) and
   quads (type 3) become VTK cells; cells listed clockwise (negative shoelace area
   $\tfrac12\sum (x_k y_{k+1} - x_{k+1} y_k)$) are reversed; the 2-node line elements of each
   physical group become the boundary faces of the patch of that name. `Mesh.from_cells` then finds
   all faces, owners and neighbours and checks that every boundary face is in a patch.

**In the code:** `aeroflowsim/gmsh_mesh.py` (`external_mesh`, `nozzle_mesh`, `_size_fields`,
`_gmsh_arrays`, `_run_gmsh`).

### 8.3 Inflation layers on unstructured meshes

Thin quad layers along walls are grown by AeroFlowSim itself (an *advancing-layer* method, as in
most CFD meshers), because Gmsh's BoundaryLayer field failed for many nozzle sizes:

1. Gmsh places the nodes along the wall (1D mesh only).
2. From every wall node a column of nodes is grown into the flow at heights
   $H_j = h(1 + g + \dots + g^{j-1})$. The column direction is the average of the two neighbouring
   wall normals, with the height stretched by $1/\cos(\text{half the turn})$ at a corner so the
   layers stay parallel to both walls ("mitre"). At a corner pointing into the flow sharper than
   60° a **fan** of columns turns from one normal to the other (the first layer there is triangles).
   Where an open wall ends on another boundary (symmetry line, axis, inlet, outlet) the column runs
   along that boundary.
3. Where neighbouring columns would cross (inward corners), the directions are smoothed by
   repeated averaging $\mathbf{d}_i \leftarrow \text{normalise}(\mathbf{d}_{i-1} + 2\mathbf{d}_i + \mathbf{d}_{i+1})$
   until no cell folds; if the layers still fold, a clear error asks for thinner layers.
4. Gmsh meshes the rest of the domain, whose inner boundary is the top of the layers (one edge per
   layer node, so the nodes match exactly).

**In the code:** `aeroflowsim/inflation_layers.py` (`grow_layers`, `_columns`, `_smooth`).

---

## 9. Geometry: rounded throat, shape library and the geometry workspace

### 9.1 Rounded throat

A throat of radius $r_t$ between cones of half-angles $\alpha_c$ (convergent) and $\alpha_d$
(divergent) is rounded by two circular arcs of radii $R_{cu} = (R_{cu}/R_t)\,r_t$ (upstream) and
$R_{cd}$ (downstream), both with their centres straight above the throat at $(x_t, r_t + R_c)$. A
point on an arc at angle $\varphi$ from the throat is

$$ x = x_t \mp R_c\sin\varphi,\qquad r = r_t + R_c(1 - \cos\varphi), $$

with slope $dr/dx = \mp\tan\varphi$. The arc is therefore **tangent** to its cone at
$\varphi = \alpha$: the tangent point is $\left(x_t \mp R_c\sin\alpha,\; r_t + R_c(1-\cos\alpha)\right)$.
At the throat ($\varphi = 0$) both arcs are horizontal, so they are tangent to each other. The
throat and exit radii stay exact; the cones shorten. The arc fits only if
$r_t + R_c(1 - \cos\alpha)$ is below the inlet (or exit) radius, i.e.
$R_c/R_t < (r_{in} - r_t)/(r_t(1 - \cos\alpha_c))$; otherwise a clear error is shown.

The exact nozzle volume used for validation adds the cylinder, the two frustums
$\frac{\pi L}{3}(r_1^2 + r_1 r_2 + r_2^2)$ and the arc sections

$$ V_{arc} = \pi\int (a - \sqrt{R_c^2 - u^2})^2\,du,\quad a = r_t + R_c,\quad
\int\sqrt{R_c^2 - u^2}\,du = \tfrac{u}{2}\sqrt{R_c^2 - u^2} + \tfrac{R_c^2}{2}\arcsin\tfrac{u}{R_c}. $$

**In the code:** `conical_nozzle`, `_rounded_throat_nozzle`, `throat_arc_end` in
`aeroflowsim/geometry.py`; `validation/external_geometry/`.

### 9.2 Shape library

Every shape returns a closed, counter-clockwise outline (`ShapeProfile`) with its sharp corners,
refinement points, reference length and reference area (planar: $L \times 1$ m; axisymmetric: base
area $\pi R^2$). Examples:

- **NACA 4-digit** (Abbott & von Doenhoff 1959, §6.4): thickness
  $y_t = 5t(0.2969\sqrt{x} - 0.1260x - 0.3516x^2 + 0.2843x^3 + a_4 x^4)$ with $a_4 = -0.1015$
  (original) or $-0.1036$ (closed trailing edge); camber line
  $y_c = \frac{m}{p^2}(2px - x^2)$ for $x < p$, $\frac{m}{(1-p)^2}((1-2p) + 2px - x^2)$ after;
  the thickness is added perpendicular to the camber line; cosine spacing $x = (1 - \cos\beta)/2$.
- **Half domains** cut the outline at $y = 0$ (after checking that the body is symmetric) and put a
  symmetry patch (planar) or an axis patch (axisymmetric) on $y = 0$.

**In the code:** `aeroflowsim/shapes/` (`profile.py`, one `.py` + `.toml` per shape, registry in
`__init__.py`).

### 9.3 The geometry workspace: a history of operations

The workspace (Geometry step) stores a geometry as the **recipe** that makes it, like the feature
tree of a CAD program: an ordered list of operations (template shape, import, sketch, transform,
fillet, boolean, enclosure, boundary name, refinement region). The geometry is obtained by
**replaying** the list from the top in the OpenCASCADE kernel (through Gmsh's `gmsh.model.occ`);
editing an earlier operation re-runs the later ones, and undo/redo swaps one list for another. The
list is saved as `geometry/history.json`. Replaying is deterministic, so the same list always gives
the same geometry (tested).

**Stable edge ids (lineage).** OpenCASCADE renumbers curves after a boolean, so boundary names
cannot refer to curve numbers. Every edge carries an id naming the operation that made it
(`op3:farfield.top`). After a topology change, each new curve is matched to the old curves
geometrically: five interior points of the new curve are compared with densely sampled old curves
(2000 points); if all five lie within $10^{-5}$ of the geometry size of one old curve, the new curve
is that curve or a piece of it (pieces numbered along it: `#1`, `#2`, ...); points on several old
curves mean a merge (`a+b`); otherwise the curve is new. A boundary name given to an id applies to
the edge, its pieces and merges, so names survive edits.

**Areas and centroids (Green's theorem).** For a face bounded by closed loops,
$$A = \tfrac12\oint (x\,dy - y\,dx),\qquad A\,x_c = \tfrac12\oint x^2\,dy,\qquad A\,y_c = -\tfrac12\oint y^2\,dx,$$
evaluated on the **exact** curves with 8-point Gauss-Legendre quadrature on 2, 4, 8 ... parameter
pieces until the result changes by less than $10^{-14}$ of the size squared. Each loop is summed in its
own direction and taken positive; holes are subtracted. (OpenCASCADE's own surface integration was
0.2 % off on scaled faces.) The volume of revolution of an axisymmetric face follows from Pappus:
$V = 2\pi A\,y_c$.

**Picking (what was clicked).** The click becomes a world point $\mathbf p$ and a tolerance of 8 pixels
in metres. The distance from $\mathbf p$ to a segment $\mathbf a \to \mathbf b$ is
$$d = \left|\mathbf a + t(\mathbf b - \mathbf a) - \mathbf p\right|,\qquad
t = \operatorname{clip}\!\left(\frac{(\mathbf p - \mathbf a)\cdot(\mathbf b - \mathbf a)}{|\mathbf b - \mathbf a|^2}, 0, 1\right),$$
computed for every segment of every edge's points; the nearest corner point within the tolerance wins,
else the nearest edge, else the smallest face containing $\mathbf p$ (even-odd ray-casting test: a ray
from $\mathbf p$ to $+x$ crosses the loops an odd number of times). Snapping while sketching moves a
click to a corner, an earlier sketch point, an edge midpoint, or the nearest grid point
($1, 2, 5 \times 10^n$, about a twentieth of the geometry).

**Healing of imported files.** Point lists lose repeated points, are closed and turned
counter-clockwise; curves (DXF, IGES/STEP wires) are glued with an OpenCASCADE *fragment* using a
tolerance ($10^{-5}$ of the size by default): ends closer than it become one point, identical curves
one curve, crossing curves are split. Closed loops are found by walking from point to point (every
point joining exactly two curves); loops inside loops become holes; open chains and branching points
are reported. CAD units: OpenCASCADE reads STEP/IGES in mm (converted from the file's unit); Gmsh's
import scaling turns that into metres exactly (lines stay lines, circles stay circles).

**Meshing an edited geometry.** Boundary names become Gmsh physical groups and therefore mesh patches.
Sizes: $h(d) = \min(h_{max}, h_w + (g-1)d)$ from the walls (as in 8.2); corners from $h_w/4$;
refinement box and circle: Gmsh *Box* and *Ball* fields, size $h_r$ inside, growing outside over
$(h_{max} - h_r)/(g - 1)$; wake line: the same ramp starting at half its width from the line. Far-field
arcs keep at least 120 faces per full circle. Inflation layers (8.3) on walls marked for them: the
nodes along the wall chain come from a 1D mesh, the layers are grown with the fluid on the right-hand
side, the region they cover is cut out of the fluid face by a boolean (neighbouring straight
boundaries are trimmed and keep their names), and Gmsh meshes the rest with one edge per layer-top
segment. An unedited template geometry still uses the template's own mesher, so validated meshes are
unchanged.

**Suggested sizes (first smart rule).** With $L$ the reference length (length along $x$ of the bodies,
or of the whole fluid region) and $\ell_{min}$ the shortest wall edge:
$h_w = \min(L/100,\ \ell_{min}/4)$; $h_{max} = \min(2L, D/20)$ around bodies or $D/25$ for internal
flow ($D$: domain diagonal); subsonic far field at least $20L$ from the body; supersonic ($M > 1$):
a rectangle $2L$ upstream (disturbances cannot travel upstream), $5L$ downstream and high enough that
Mach waves at $\mu = \arcsin(1/M)$ leave through the outlet: $H \ge \tan\mu\,(2 + 1 + 5)L + L$.
Every suggestion is shown with its reason and applied only by the user.

**In the code:** `aeroflowsim/geometry_model/` (`document.py` replay, `kernel.py` lineage and
`face_integrals`, `picking.py`, `snapping.py`, `healing.py`, `importers.py`, `export.py`),
`aeroflowsim/workspace_mesh.py`, `aeroflowsim/smart_rules.py`, geometry checks in `aeroflowsim/checks.py`.

---

## 10. Reproducibility: projects, fingerprints and background runs

Numerical results are only useful if one can say *exactly* which inputs produced them. AeroFlowSim
therefore separates the physics (a **template**, `cases/<name>/`) from the user's work (a **project**,
a folder `<name>.afsproj/`), and records for every product (mesh, run) a **fingerprint** of what it
was made from.

**Fingerprint.** For a product $P$ (mesh or run) with input set $I_P$,

$$F_P = \mathrm{SHA256}\big(\,T \,\|\, v \,\|\, P \,\|\, (k, x_k)_{k \in I_P} \,\|\, \text{bytes of every input file in } I_P\big),$$

where $T$ is the SHA-256 of the template's `schema.toml` and `case.py`, $v$ the AeroFlowSim version
and $(k, x_k)$ the input names and values in schema order. The input sets are nested,

$$I_\text{mesh} = I_\text{geometry} \cup I_\text{mesh inputs}, \qquad I_\text{run} = I_\text{geometry} \cup I_\text{mesh inputs} \cup I_\text{setup},$$

so any change upstream changes every fingerprint downstream. A product is **up to date** when its
stored fingerprint equals the one computed from today's inputs, **out of date** otherwise. SHA-256 is a
cryptographic hash: two different input sets giving the same fingerprint is, for all practical
purposes, impossible ($2^{-128}$ collision resistance). Line endings in files are normalised first,
so a project gives the same fingerprints on Windows and Linux. Because the mesh generators and
solvers are deterministic, equal fingerprints imply equal meshes and results; going back to earlier
inputs (e.g. with Undo) makes old results current again without recomputing.

**Exact storage.** Results are saved as NumPy arrays (`results/run.npz`), bit-for-bit, together with
the inputs; a project folder copied to another computer reopens with the same numbers, and a new run
from it reproduces them exactly (tested). No Python pickle is used, so opening a shared project can
never execute code.

**Background runs.** Meshing and solving run in a separate operating-system process that calls the
same engine (`aeroflowsim.run_case`) as the command line, with the same inputs; process boundaries do
not change floating-point results, so GUI, command line and scripts give identical numbers (tested
array-for-array). Stopping a run raises an exception between two iterations, so no half-updated
solution is ever stored.

**In the code:** `aeroflowsim/project.py` (`Project.fingerprint`, `Project.status`),
`aeroflowsim/result_io.py` (`save_run`, `load_run`), `aeroflowsim/tasks.py` (`Worker`, `_run_job`).
The GUI side is described in `docs/developer_guide.md`.

---

## 11. Gas models

Every solver gets its gas properties through one interface, `GasModel`, and never writes a number such
as $\gamma = 1.4$ itself. The interface asks for the specific gas constant $R$, $c_p(T)$, $c_v(T)$,
$\gamma(T)$, the speed of sound, the internal energy $e(T)$ and its inverse $T(e)$, the viscosity
$\mu(T)$, the conductivity $k(T)$, the Prandtl number and the temperature ranges where the data are
valid. Each method takes one temperature or an array (one per cell). A new gas model (thermally
perfect, mixture, real gas) is a new subclass; no solver changes.

### 11.1 Calorically perfect gas

The model implemented now is the ideal gas with constant specific heats:

$$p = \rho R T,\qquad R = \frac{R_u}{M},\qquad c_p = \frac{\gamma R}{\gamma - 1},\qquad c_v = \frac{R}{\gamma - 1},$$

$$e = c_v T,\qquad h = c_p T,\qquad c = \sqrt{\gamma R T},$$

with $R_u = 8.314462618$ J/(mol K) (CODATA 2018, exact) and $M$ the molar mass. A solver that
carries the total energy $E = \rho(e + u^2/2)$ gets $T$ back with $T(e) = e / c_v$. For the 2D solver
(Prompt 7) this is the only place where the gas enters the flux and the boundary conditions:
$p = (\gamma - 1)(E - \rho u^2/2)$, $c = \sqrt{\gamma p/\rho}$, and the inlet's total-to-static
relations, all with $\gamma$ and $R$ from the model.

**Data and their sources.** One TOML file per gas (`aeroflowsim/gases/<id>.toml`), every value with
its source. $M$, the critical point and the acentric factor come from the NIST Chemistry WebBook
(Lemmon et al.); $\gamma$ is $c_p/c_v$ of the NIST equation of state at 300 K and 0.1 kPa (the
ideal-gas limit), rounded to 4 decimals, and exactly 5/3 for the monatomic gases (kinetic theory:
$c_p = \tfrac52 R$). Two values are kept from the validated quasi-1D case: N2 uses the 4-figure table
values $\gamma = 1.4$ and $R = 296.8$ J/(kg K) (NIST: $c_p/c_v = 1.3995$ at 300 K, $R_u/M = 296.803$),
differences far below every tolerance, so the validated numbers stay bit-identical. Air follows the
U.S. Standard Atmosphere 1976 ($M = 28.9644$ g/mol, $R = 287.053$ J/(kg K), $\gamma = 1.4$).

**Valid temperature range.** Constant $c_p$ is a good model only where the real $c_p$ hardly changes.
The range stored for each gas is the interval around 300 K where the NIST $c_p$ (0.1 kPa) stays
within 2 % of the constant one. Diatomic gases are good from the triple point to about 500 K (N2:
63-521 K), until the vibrational modes start; CO2 and R-236fa only within about 15 K of room
temperature, because their vibrational $c_p$ changes already near room temperature. The
temperature-range check (11.5) warns when a solution leaves this range.

### 11.2 Viscosity and thermal conductivity

Sutherland's law (Sutherland 1893; White 2006) and a power law:

$$\mu(T) = \mu_\text{ref}\left(\frac{T}{T_\text{ref}}\right)^{3/2}\frac{T_\text{ref} + S}{T + S},\qquad
\mu(T) = \mu_\text{ref}\left(\frac{T}{T_\text{ref}}\right)^{n},$$

and the same forms for $k$. Without a conductivity law, $k = \mu c_p / \mathrm{Pr}$ with a constant
Prandtl number. The constants of the built-in gases are **fitted** to the NIST transport data at
0.1 kPa by least squares on the relative error, $\min \sum_i (\mu_\text{law}(T_i)/\mu_i - 1)^2$; for
each gas the law (Sutherland or power) and the widest range around 300 K within 2 % of the data are
kept, and the file states the range and the largest deviation. (White's classic constants agree with
NIST for N2 and O2 but are several percent off for argon and steam, so a fit to one reference data
set is more consistent.) Air uses the Sutherland law of the U.S. Standard Atmosphere
($\mu = 1.458\times10^{-6}\, T^{1.5}/(T + 110.4)$) and White's conductivity constants, checked
against the Standard Atmosphere conductivity within 2 % from 170 to 920 K. The Euler solvers do not
use $\mu$ and $k$; they are ready for Navier-Stokes (Phase 4).

### 11.3 Ideal-gas validity: compressibility factor (Peng-Robinson)

The ideal-gas law ignores the size of molecules and their attraction. The compressibility factor
$Z = p/(\rho R T)$ measures the error ($Z = 1$ for an ideal gas). It is estimated with the
Peng-Robinson equation of state (Peng & Robinson 1976):

$$p = \frac{R_u T}{v - b} - \frac{a\,\alpha(T)}{v^2 + 2bv - b^2},\qquad
a = 0.45724\,\frac{R_u^2 T_c^2}{p_c},\qquad b = 0.07780\,\frac{R_u T_c}{p_c},$$

$$\alpha = \left[1 + \kappa\left(1 - \sqrt{T/T_c}\right)\right]^2,\qquad
\kappa = 0.37464 + 1.54226\,\omega - 0.26992\,\omega^2,$$

with molar volume $v$, critical temperature $T_c$, critical pressure $p_c$ and acentric factor
$\omega$. With $A = a\alpha p/(R_u T)^2$ and $B = bp/(R_u T)$ it becomes a cubic in $Z$,

$$Z^3 - (1 - B)Z^2 + (A - 3B^2 - 2B)Z - (AB - B^2 - B^3) = 0,$$

whose largest real root is the gas. **Accuracy** (against the NIST reference equations):

| State | NIST $Z$ | Peng-Robinson $Z$ |
|---|---:|---:|
| N2, 50 bar, 293.15 K | 0.9940 | 0.9836 |
| N2, 300 bar, 293.15 K (a 300 bar tank) | 1.140 | 1.092 |
| R-236fa, saturated vapour at 20 °C (2.29 bar) | 0.918 | 0.926 |

So Peng-Robinson finds the trend and is good to about 1 % in $Z$ at moderate density, but at 300 bar
N2 is as dense as at its critical point and the estimate of $|Z - 1|$ is too small (9 % instead of
14 %). That is enough for a warning threshold of 2 %, not for computing with; a real-gas solver model
(Phase 5) will use a better equation of state.

### 11.4 Condensation risk: saturation and frost curves

Each gas file stores about 30 points of the NIST saturation curve $p_\text{sat}(T)$, from the triple
point to the critical point. Between points $\ln p$ is interpolated linearly in $1/T$, the form of the
Clausius-Clapeyron equation (error below 0.25 % against the full NIST table):

$$\frac{d \ln p_\text{sat}}{d(1/T)} = -\frac{h_\text{vap}}{R_u}\quad\Rightarrow\quad
\ln\frac{p}{p_t} = -\frac{h}{R_u}\left(\frac{1}{T} - \frac{1}{T_t}\right).$$

**Below the triple point** ($p < p_t$, e.g. the N2 nozzle exit: 3.37 kPa < 12.5 kPa) the gas would
freeze directly to a solid, along the sublimation (frost) curve, whose enthalpy is
$h_\text{sub} = h_\text{vap} + h_\text{fus}$. No sourced sublimation curve is stored yet, so the
curve is continued with $h = h_\text{vap}(T_t)$ (from the slope of the first stored interval). The true
frost curve is steeper, so the true frost temperature is higher and the computed margin is an
**upper limit**. For N2: $h_\text{vap}(T_t) = 6.08$ kJ/mol (from the NIST curve) and
$h_\text{fus} \approx 0.72$ kJ/mol (CRC Handbook) give a frost temperature at 3.37 kPa of 56.7 K
(estimate) versus 57.3 K, a difference of 0.6 K.

The check computes the margin $\Delta T = T - T_\text{sat}(p)$ in every cell (and the reservoir); a
negative margin means the gas is colder than its saturation temperature and may condense, which this
model does not include. **For the default N2 nozzle:** exit $T = 70.3$ K at $p = 3.37$ kPa, frost
temperature about 56.7 K, margin **13.6 K**, so no condensation is expected. In a real expanding jet,
condensation needs some supercooling (nucleation), so a small negative margin does not always mean
droplets. A 300 bar chamber at room temperature, however, expands to about 70 K at 2 bar, deep in the
liquid region: the check warns.

### 11.5 Temperature range

The third check compares the smallest and largest temperature in the solution (and the reservoir)
with the thermodynamic range of the gas (11.1). Inviscid solvers use only that range; viscous solvers
will also check the transport range (11.2).

**In the code:** `aeroflowsim/gases/model.py` (`GasModel`, `CaloricallyPerfectGas`, `TransportLaw`),
`aeroflowsim/gases/data.py` (file format, `VapourPressure.p_sat` / `T_sat`), `aeroflowsim/gases/real_gas.py`
(`peng_robinson_z`), `aeroflowsim/gases/library.py` (built-in, user and project gases), the checks
`ideal_gas_validity`, `condensation_risk` and `temperature_range` in `aeroflowsim/checks.py`, and the
data tool `tools/gas_data/make_gas_files.py` (fits and source tables).

---

## 12. References

- Abbott, I. H., von Doenhoff, A. E. (1959). *Theory of Wing Sections*. Dover.
- Anderson, J. D. (2003). *Modern Compressible Flow*, 3rd ed. McGraw-Hill.
- Cengel, Y. A., Boles, M. A. *Thermodynamics: An Engineering Approach*. McGraw-Hill (Table A-1: gas constants).
- Blazek, J. (2015). *Computational Fluid Dynamics: Principles and Applications*, 3rd ed. Elsevier.
- Geuzaine, C., Remacle, J.-F. (2009). Gmsh: a 3-D finite element mesh generator with built-in pre- and
  post-processing facilities. *Int. J. Numer. Meth. Engng.* 79(11), 1309-1331.
- Gottlieb, S., Shu, C.-W. (1998). Total variation diminishing Runge-Kutta schemes. *Math. Comp.* 67, 73-85.
- Haynes, W. M. (ed.). *CRC Handbook of Chemistry and Physics*. CRC Press (enthalpy of fusion of N2, about 0.72 kJ/mol).
- Lemmon, E. W., McLinden, M. O., Friend, D. G. Thermophysical Properties of Fluid Systems. In *NIST Chemistry WebBook*, NIST Standard Reference Database 69 (Linstrom, P. J., Mallard, W. G., eds.). (The equation of state and transport correlations used for each gas are named in its gas file.)
- Lemmon, E. W., Jacobsen, R. T., Penoncello, S. G., Friend, D. G. (2000). Thermodynamic properties of air and mixtures of nitrogen, argon, and oxygen from 60 to 2000 K at pressures to 2000 MPa. *J. Phys. Chem. Ref. Data* 29, 331-385.
- McBride, B. J., Zehe, M. J., Gordon, S. (2002). *NASA Glenn coefficients for calculating thermodynamic properties of individual species*. NASA TP-2002-211556 (NASA polynomials; the 7-coefficient sets stored are those of GRI-Mech 3.0, Smith et al.).
- Moitzi, M. *ezdxf: a Python package to create and modify DXF documents*, version 1.4 (MIT licence).
- Open Cascade SAS. *Open CASCADE Technology*, version 7.9 (used through Gmsh's OCC interface).
- Moukalled, F., Mangani, L., Darwish, M. (2016). *The Finite Volume Method in Computational Fluid
  Dynamics*. Springer.
- Peng, D.-Y., Robinson, D. B. (1976). A new two-constant equation of state. *Ind. Eng. Chem. Fundam.* 15(1), 59-64.
- Sutherland, W. (1893). The viscosity of gases and molecular force. *Phil. Mag.* 36, 507-531.
- Toro, E. F. (2009). *Riemann Solvers and Numerical Methods for Fluid Dynamics*, 3rd ed. Springer.
- Toro, E. F., Spruce, M., Speares, W. (1994). Restoration of the contact surface in the HLL-Riemann
  solver. *Shock Waves* 4, 25-34.
- U.S. Standard Atmosphere, 1976. NOAA, NASA, USAF, NASA-TM-X-74335.
- van Leer, B. (1979). Towards the ultimate conservative difference scheme V. A second-order sequel to
  Godunov's method. *J. Comput. Phys.* 32, 101-136.
- White, F. M. (2006). *Viscous Fluid Flow*, 3rd ed. McGraw-Hill (Sutherland constants, Tables 1-2 and 1-3).
