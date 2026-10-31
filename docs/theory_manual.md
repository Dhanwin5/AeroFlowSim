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
12. [The 2D / axisymmetric Euler solver](#12-the-2d--axisymmetric-euler-solver)
13. [Verification, post-processing and the new validation cases](#13-verification-post-processing-and-the-new-validation-cases-prompt-7b)
14. [New shapes, nozzle contours and intakes](#14-new-shapes-nozzle-contours-and-intakes-prompt-6e-part-1)
15. [The optional assistant: it assists, it never replaces physics](#15-the-optional-assistant-it-assists-it-never-replaces-physics)
16. [References](#16-references)

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
Quasi-1D: `quasi1d_rhs` in `aeroflowsim/quasi1d.py`. The face-based form for 2D/3D: `aeroflowsim/euler/solver.py`
(Section 12) on the mesh of Section 7.

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
"carbuncle" instability of strong bow shocks aligned with the mesh, fixed in the 2D solver (Section 12.2).

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

On unstructured meshes the slope becomes a cell gradient (least squares or Green-Gauss) and the limiter a
multidimensional one (Barth-Jespersen or Venkatakrishnan): Section 12.3-12.4.

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

## 12. The 2D / axisymmetric Euler solver

The finite-volume Euler solver of `aeroflowsim/euler/` works on the face-based mesh of Section 7, so the
same code solves planar 2D and axisymmetric flow today and 3D flow later: states have $d + 2$ rows
($\rho$, $d$ velocity components, $p$), with the number of space dimensions $d$ taken from the mesh,
and every operation is a loop over faces (NumPy arrays, no Python loop over cells or faces).

### 12.1 Finite-volume form, planar and axisymmetric

For cell $i$ (Section 2):

$$ V_i \frac{d\mathbf{U}_i}{dt} = -\sum_f \hat{\mathbf{F}}(\mathbf{W}_L, \mathbf{W}_R; \mathbf{n}_f)\, A_f + \mathbf{S}_i . $$

**Planar 2D:** $A_f$ = edge length × 1 m, $V_i$ = cell area × 1 m, $\mathbf{S}_i = 0$.

**Axisymmetric** (axis along $x$, $r = y \ge 0$): integrating over one radian of the revolved cell gives
$A_f = $ edge length × $r_f$ (face centre) and $V_i$ = cell area × $r_i$ (centroid), both exact for straight
edges (theorem of Pappus; `mesh.axi_face_areas`, `mesh.axi_cell_volumes`). The pressure on the two flat
sides of the one-radian wedge pushes outward in $r$: $\mathbf{S}_i = (0,\, 0,\, p_i \mathcal{A}_i,\, 0)$ with
$\mathcal{A}_i$ the planar cell area. Faces on the axis have $r_f = 0$, so no flux passes them and no special
treatment is needed.

**Well-balanced source.** For gas at rest the face fluxes are $p\,\mathbf{n}_f A_f$ and must cancel the
source exactly, otherwise round-off "winds" appear. For straight edges
$\sum_f n_{r,f}\, r_f L_f = \mathcal{A}_i$ and $\sum_f n_{x,f}\, r_f L_f = 0$ exactly (divergence theorem), so the
solver computes the geometric vector $\mathbf{G}_i = \sum_f \mathbf{n}_f A_f$ once and writes the momentum equation as

$$ V_i \frac{d(\rho\mathbf{u})_i}{dt} = -\sum_f \left(\hat{\mathbf{F}}_{\rho\mathbf{u},f} - p_i\,\mathbf{n}_f\right) A_f . $$

For a planar (closed) cell $\mathbf{G}_i = 0$, so nothing changes; for an axisymmetric cell $p_i \mathbf{G}_i$
*is* the pressure source. Gas at rest gives zero in every bracket: it stays at rest to round-off on every
mesh type (tested). This is the 2D version of the quasi-1D form of Section 6.

### 12.2 HLLC in the face-normal frame, and the carbuncle fix

At a face with unit normal $\mathbf{n}$ only the normal velocity $u_n = \mathbf{u}\cdot\mathbf{n}$ carries mass
through it. The 1D HLLC solver of Section 3 is applied along $\mathbf{n}$ ("rotate, solve, rotate back"),
written with vectors so that no rotation matrix is needed and the same code works in 3D:

$$ \mathbf{F}\cdot\mathbf{n} = \begin{pmatrix}\rho u_n\\ \rho\mathbf{u}\,u_n + p\,\mathbf{n}\\ (E+p)u_n\end{pmatrix},\qquad
\mathbf{U}_{*K} = \rho_K\frac{S_K - u_{n,K}}{S_K - S_*}\begin{pmatrix}1\\ \mathbf{u}_K + (S_* - u_{n,K})\,\mathbf{n}\\
\dfrac{E_K}{\rho_K} + (S_* - u_{n,K})\left(S_* + \dfrac{p_K}{\rho_K(S_K - u_{n,K})}\right)\end{pmatrix}. $$

Only the normal velocity changes to $S_*$ in the star states; the tangential velocity is carried across
the contact (so shear layers stay sharp). **Wave speeds** are Einfeldt's (1988) estimate from
$\sqrt\rho$-weighted averages,

$$ S_L = \min(u_{n,L} - c_L,\; \bar u_n - \bar d),\quad S_R = \max(u_{n,R} + c_R,\; \bar u_n + \bar d),\quad
\bar d^2 = \frac{\sqrt{\rho_L}c_L^2 + \sqrt{\rho_R}c_R^2}{\sqrt{\rho_L}+\sqrt{\rho_R}} + \eta_2 (u_{n,R} - u_{n,L})^2 , $$

$\eta_2 = \tfrac12\sqrt{\rho_L\rho_R}/(\sqrt{\rho_L}+\sqrt{\rho_R})^2$, which needs only the speeds of sound (no
$\gamma$), so every gas model works. All gas properties come from the `GasModel` (Section 11):
$T = T(e)$ with $e = E/\rho - |\mathbf{u}|^2/2$, $p = \rho R T$, $c = c(T)$.

**Carbuncle.** At a strong shock aligned with the mesh, HLLC's exact contact resolution lets
disturbances travel along the shock front undamped; the shock then grows a spurious bulge
(the "carbuncle", Quirk 1994). HLLE (HLL with Einfeldt's speeds) is free of it but smears contacts. The
fix used here is Quirk's shock-aware hybrid: a pressure sensor per face
$s_f = |p_R - p_L| / \min(p_L, p_R)$, counted only where the pressure rises in the direction of the flow through
the face (a compression; strong expansions such as the flow round a sharp nozzle throat keep pure HLLC), per cell the largest $s_f$ of its faces, per face the larger of its two
cells, and a smooth blend weight $w = \text{clip}((s - 0.5)/(1.0 - 0.5), 0, 1)$ with

$$ \hat{\mathbf{F}} = (1 - w)\,\hat{\mathbf{F}}_\text{HLLC} + w\,\hat{\mathbf{F}}_\text{HLLE}. $$

So HLLE acts only in a band about two cells wide around shocks with a pressure ratio above about 1.5
per face; weak waves, contacts and smooth flow keep pure HLLC. The blend is smooth (not an on/off
switch), so it does not stall steady convergence. (The rotated hybrid of Nishikawa & Kitamura 2008 is
the same idea with the HLLE direction chosen along the velocity jump.) Verified by the Mach 6 cylinder
of Section 12.9.

### 12.3 Weighted least-squares gradients

In cell $i$ the gradient $\mathbf{g}$ minimises the misfit to the face neighbours $j$ (Blazek 2015, sec. 5.3.3):

$$ \min_\mathbf{g} \sum_j w_j^2\left(\mathbf{g}\cdot\mathbf{d}_j - (\phi_j - \phi_i)\right)^2,\quad w_j = \frac1{|\mathbf{d}_j|}
\quad\Rightarrow\quad \mathbf{g} = \mathsf{A}^{-1}\sum_j w_j^2\,\mathbf{d}_j(\phi_j - \phi_i),\quad \mathsf{A} = \sum_j w_j^2\,\mathbf{d}_j\mathbf{d}_j^T . $$

$\mathbf{d}_j$ points from the cell centre to the neighbour centre; at a boundary face the "neighbour" is the
boundary value at the face centre (the mean of the inside and ghost states of 12.6). $\mathsf{A}$ ($d\times d$)
depends only on the mesh, so the coefficients $\mathsf{A}^{-1}w_j^2\mathbf{d}_j$ are stored once as a sparse matrix and
each gradient evaluation is one sparse product. A linear field is reproduced exactly on any cell shape
(tested on distorted quads, triangles, hybrid meshes and single hexahedra and tetrahedra).
**Green-Gauss** (option): $\mathbf{g} = \frac1V\sum_f \tfrac12(\phi_i + \phi_j)\,\mathbf{n}_f A_f$, simpler but
exact only on regular meshes.

### 12.4 Limiters, and freezing

The face value is $\phi_f = \phi_i + \psi_i\,\mathbf{g}_i\cdot\mathbf{r}_f$ ($\mathbf{r}_f$: cell centre to face centre). With
$\Delta = \mathbf{g}_i\cdot\mathbf{r}_f$ and $D = \phi_\max - \phi_i$ (if $\Delta > 0$) or $\phi_\min - \phi_i$ (if $\Delta < 0$), the
extremes taken over the cell and its face neighbours:

$$ \text{Barth-Jespersen: } \psi_f = \min\!\left(1, \frac{D}{\Delta}\right),\qquad
\text{Venkatakrishnan: } \psi_f = \frac{1}{\Delta}\,\frac{(D^2 + \varepsilon^2)\Delta + 2\Delta^2 D}{D^2 + 2\Delta^2 + D\Delta + \varepsilon^2}, $$

and $\psi_i = \min_f \psi_f$. Venkatakrishnan's (1995) limiter is smooth, which steady convergence needs;
$\varepsilon^2$ lets small differences through unlimited. The textbook $\varepsilon^2 = (K h)^3$ is not dimensionally
consistent; AeroFlowSim uses the non-dimensional form $\varepsilon^2 = (K h / L_\text{ref})^3\,\phi_\text{ref}^2$ with $h$ the
cell size, $L_\text{ref}$ the throat diameter or body length and $\phi_\text{ref}$ a reference size of the variable
(free-stream or reservoir values); $K = 5$ by default. **Freezing:** once the residual has dropped a set
number of orders (default 4), $\psi$ is kept fixed. A limiter that keeps switching in a few cells can stall
the residual (exactly what the quasi-1D minmod limiter does on fine meshes, Section 6 and the gap
register); frozen, the scheme is a fixed linear one there and converges.

### 12.5 Positivity fallback

If a reconstructed face state has $\rho \le 0$ or $p \le 0$ on either side, that face uses the first-order
states (the cell values). The number of such faces is counted every iteration and reported (monitor,
Positivity validity check). Events during the start-up are normal; events in the last iteration mean
that part of the solution is only first-order accurate.

### 12.6 Boundary conditions (ghost states)

A boundary face has a cell on one side only. The boundary condition supplies a **ghost** state
$\mathbf{W}_g$ on the other side, and the same Riemann solver gives the boundary flux. How many quantities may
be imposed follows the characteristics: the number of waves entering the domain.

| Type | Ghost state |
|---|---|
| Slip wall, symmetry, axis | mirror: $\mathbf{u}_g = \mathbf{u}_i - 2(\mathbf{u}_i\cdot\mathbf{n})\mathbf{n}$, same $\rho$, $p$; HLLC then gives zero mass flux and the wall pressure |
| Supersonic inlet | everything imposed: $M$, $p$, $T$, direction |
| Supersonic outlet | everything from inside: $\mathbf{W}_g = \mathbf{W}_i$ |
| Far field | Riemann invariants along $\mathbf{n}$: $R^+ = u_{n,i} + \frac{2c_i}{\gamma-1}$ (outgoing, inside), $R^- = u_{n,\infty} - \frac{2c_\infty}{\gamma-1}$ (incoming, free stream); $u_{n,b} = \frac{R^+ + R^-}2$, $c_b = \frac{\gamma-1}4(R^+ - R^-)$; entropy $p/\rho^\gamma$ and tangential velocity from the free stream at inflow faces, from inside at outflow faces; supersonic faces all free stream (in) or all inside (out) (Blazek sec. 8.5) |
| Total-pressure inlet | $p_0$, $T_0$, direction imposed; speed from inside (projected on the direction, $\ge 0$); $T = T_0 - |\mathbf{u}|^2/2c_p$, $p = p_0 (T/T_0)^{\gamma/(\gamma-1)}$ (as the quasi-1D inlet) |
| Mass-flow inlet | $\dot m$, $T_0$ imposed, $p$ from inside; $G = \dot m/A_\text{patch}$, $\rho u = G$, $T = T_0 - u^2/2c_p$ give $a u^2 + u - b = 0$ with $a = GR/(2c_p p)$, $b = G R T_0/p$ |
| Pressure outlet | subsonic: $p_b$ imposed, $\rho_b = \rho_i + (p_b - p_i)/c^2$, $\mathbf{u}_b = \mathbf{u}_i + \mathbf{n}(p_i - p_b)/(\rho c)$ (Blazek eq. 8.30); supersonic faces ($u_n \ge c$): everything from inside, automatically |

For the gradients the boundary value at the face centre is $\tfrac12(\mathbf{W}_i + \mathbf{W}_g)$ with the ghost of the
cell value; for the flux the ghost is built from the reconstructed face state. Each named boundary of the
mesh gets one condition (Setup table): the template's default for its kind (inlet, outlet, wall, far field,
symmetry, axis) unless the user changes it.

### 12.7 Time stepping, local time steps and robustness

**SSP-RK3** (Shu & Osher 1988; default):
$\mathbf{U}^{(1)} = \mathbf{U}^n + \Delta t\,\mathbf{L}(\mathbf{U}^n)$,
$\mathbf{U}^{(2)} = \tfrac34\mathbf{U}^n + \tfrac14(\mathbf{U}^{(1)} + \Delta t\,\mathbf{L}(\mathbf{U}^{(1)}))$,
$\mathbf{U}^{n+1} = \tfrac13\mathbf{U}^n + \tfrac23(\mathbf{U}^{(2)} + \Delta t\,\mathbf{L}(\mathbf{U}^{(2)}))$.
**Jameson four-stage** (Jameson, Schmidt & Turkel 1981; option for steady runs):
$\mathbf{U}^{(k)} = \mathbf{U}^n + \alpha_k\Delta t\,\mathbf{L}(\mathbf{U}^{(k-1)})$, $\alpha = \tfrac14, \tfrac13, \tfrac12, 1$, stable to a larger CFL.

**Time step** per cell (Blazek eq. 6.22): $\Delta t_i = \text{CFL}\; \mathcal{V}_i/\Lambda_i$ with
$\Lambda_i = \tfrac12\sum_f(|\mathbf{u}_i\cdot\mathbf{n}_f| + c_i)\,\mathcal{A}_f$ (planar areas and volumes, also for
axisymmetric meshes). Steady runs use these **local** steps; time-accurate runs (the 2D shock tube) use the
smallest one everywhere and stop exactly at the end time.

**Robust start:** an optional number of first-order iterations before second order. **CFL back-off:** if a
step produces a negative density or pressure (or NaN), the last good state (saved every 20 iterations) is
restored and the CFL number halved, at most 4 times; then the run stops cleanly as *diverged*, keeps the last
good state, reports where it failed and the smart rule suggests what to change (12.10). **Stop** (the user)
ends the run after the current iteration with the flow of that moment (status *stopped*, not converged), which
can be inspected. **Run carries on** from the current solution on the same mesh: the iterations are numbered on
(159 after 158), the residuals keep their normalisation and the residual and monitor histories continue, so the
convergence criteria see the whole run, and a frozen limiter stays frozen; *Maximum iterations* counts the whole
run. Only *Start from scratch* (or a new mesh) begins again from the initial solution. A **setup check** refuses an angle of attack on
an axisymmetric mesh before the run: an axisymmetric flow is the same all round the axis.

### 12.8 Residuals, monitors and convergence

The residual of each equation is the RMS over the cells of $d\mathbf{U}/dt$, normalised by its largest value in
the first five iterations. **Monitors** are integrated quantities recorded every iteration: mass flow in
and out and the thrust two ways (nozzles), Cd, Cl, Cm (bodies). A steady run has **converged** when the
largest normalised residual is below the tolerance (default $10^{-6}$) **and** every convergence monitor
changed less than the monitor tolerance (default $10^{-4}$, relative) over the monitor window (default
500 iterations). Iterations and wall-clock time are reported (CLAUDE.md rule 14).

### 12.9 Integrated quantities

All are sums of the boundary fluxes the solver has just used (so balances close exactly when converged);
axisymmetric values × $2\pi$, planar values per metre of depth.

- **Mass flow** through a boundary: $\dot m = \sum_f \hat F_{\rho,f} A_f$.
- **Thrust two ways** (vacuum): exit plane $F = \sum_\text{exit} (\rho u_x u_n + p\,n_x)A$ $= \dot m u_e + p_e A_e$;
  wall + inlet $F = -\sum_\text{inlet}(\rho u_x u_n + p\,n_x)A - \sum_\text{wall} p\,n_x A$ (steady x-momentum balance;
  the axisymmetric source acts in $r$ only). At a back pressure: $F - p_a A_e$. $I_{sp} = F/(\dot m g_0)$,
  $C_F = F/(p_0 A_t)$, discharge coefficient $C_d = \dot m / \dot m_\text{1D}$ with the ideal choked mass flow
  of the throat. The quasi-1D comparison uses the ideal isentropic Isp of the same wall.
- **Body forces:** $\mathbf{F} = \sum_\text{wall}(p - p_\infty)\,\mathbf{n} A$ (zero for a closed body when $p = p_\infty$; correct for
  half bodies); drag along and lift normal to the free stream; $C_D = D/(q_\infty A_\text{ref})$,
  $C_L = L/(q_\infty A_\text{ref})$, $C_M = M/(q_\infty A_\text{ref} L_\text{ref})$ about the quarter-length point,
  $C_p = (p - p_\infty)/q_\infty$ along the wall.

### 12.10 Validity checks and smart rules of a run

Checks (`aeroflowsim/checks.py`, `FLOW_CHECKS`): run status (diverged = error), monitors settled, thrust two ways
(within 0.5 %), total-pressure loss (an isentropic nozzle or shock-free external flow should lose none: a
classic accuracy indicator), positivity events, CFL reductions; plus the existing convergence, mass balance,
gas and mesh checks. Smart rules (`aeroflowsim/smart_rules.py`): before a run, CFL and first-order start from
the Mach number (strong bow shocks: CFL 0.5, 500 first-order iterations) and the quasi-1D start for nozzles;
the first-layer height for $y^+ = 1$ from the flow's Reynolds number ($C_f = 0.026\,Re^{-1/7}$, White 2006);
after a diverged run, what to try (lower CFL, first-order start, quasi-1D start, check the boundary values,
refine at the throat if it failed there). Suggestions are only applied by the user.

### 12.11 Verification

| Test | What it shows |
|---|---|
| Free stream on quads, distorted quads, triangles, hybrid meshes | uniform flow stays uniform to round-off ($10^{-15}$) |
| Gas at rest, axisymmetric (structured, triangles, quad-dominant, inflation) | velocity stays at round-off: the source is well-balanced |
| Linear fields | least-squares gradients exact on every cell type, also single 3D cells |
| Equal states, swapped sides, rotation | flux consistency, conservation, rotation invariance (2D and 3D) |
| Boundary conditions | ghost states, and small runs reaching the exact uniform solution |
| 2D shock tube along x and along a triangle-mesh diagonal | exact Riemann solution (validation report) |

**In the code:** `aeroflowsim/euler/` (`state.py`, `flux.py`, `geometry.py`, `gradients.py`, `limiters.py`,
`boundary.py`, `solver.py`, `forces.py`, `initial.py`, `setup.py`); tests `tests/test_euler_core.py`,
`tests/test_euler_boundaries.py`, `tests/test_flow_checks.py`; validation `validation/euler2d_*`.

---

## 13. Verification, post-processing and the new validation cases (Prompt 7b)

### 13.1 Method of Manufactured Solutions (`aeroflowsim/mms.py`)

A manufactured flow W_m(x, y) of the form of Roy et al. (2004),

    phi = phi_0 + phi_x f(a_x pi x / L) + phi_y g(a_y pi y / L)      (f, g = sin or cos)

for rho, u, v, p (constants chosen so the Mach number ranges from about 0.5 to 1.6), is put into the Euler
equations. What is left is the source term

    planar:        S = dF/dx + dG/dy
    axisymmetric:  S = r (dF/dx + dG/dr) + G - (0, 0, p, 0)       (r = y, per radian)

with F = (rho u, rho u² + p, rho u v, u (E + p)), G = (rho v, rho u v, rho v² + p, v (E + p)),
E = rho e(T) + rho |V|²/2. The derivatives are written out with the product and chain rules
(`mms.source`; dE = e drho + rho cv dT + rho (u du + v dv), dT = (dp rho - p drho) / (rho² R)); a test checks them
against finite differences. The solver integrates S over each cell by the midpoint rule (S at the centroid times
the cell area: second order) through the hook `EulerSolver.source`. Boundary conditions are the exact solution:
ghost state and the boundary value of the gradients both equal W_m at the face centre (`MMSSolver`).

Each mesh is solved from the exact solution to a residual drop of 8 orders; the error e = W_h - W_m(x_c) is measured
in L1, L2 and Linf (area weighted) and the observed order between levels with ratio 2 is
p = ln(e_coarse / e_fine) / ln 2. Results (full validation set of 26 October 2026; `validation/report.md`):

| Mesh | planar, 2nd order, no limiter (64 -> 128) | axisymmetric (64 -> 128) | first order (32 -> 64) | Venkatakrishnan (32 -> 64) |
|---|---|---|---|---|
| quads | 1.98 - 2.01 | 2.02 - 2.07 | 0.84 - 0.95 | 1.01 - 1.67 |
| distorted quads | 1.98 - 1.99 | 2.02 - 2.08 | 0.66 - 0.89 | 1.24 - 1.84 |
| triangles | 2.00 - 2.12 | 2.02 - 2.08 | 0.91 - 0.98 | 1.08 - 1.34 |
| mixed | 1.99 - 2.02 | 2.00 - 2.04 | 0.94 - 0.98 | 1.07 - 1.29 |

(ranges over rho, u, v, p in L2). The scheme is second-order accurate on every cell type and in axisymmetric form
(including the well-balanced pressure source). With Venkatakrishnan's limiter the order stays near 1-1.6 and does
not approach 2 under refinement: its threshold eps² = (K h / L)³ scale² falls like h³ while the squared cell-to-cell
differences of a smooth field fall like h², so smooth extrema are clipped more and more (Michalak and
Ollivier-Gooch 2008 discuss this and an order-preserving alternative). For smooth flows on fine meshes use the
limiter "None" or a larger K.

### 13.2 Grid Convergence Index (`aeroflowsim/gci.py`)

From three meshes h1 < h2 < h3 with values phi1, phi2, phi3 (Roache 1998; Celik et al. 2008):
e21 = phi2 - phi1, e32 = phi3 - phi2, r21 = h2/h1, r32 = h3/h2,

    p = |ln|e32/e21| + q(p)| / ln r21,   q(p) = ln((r21^p - s)/(r32^p - s)),  s = sign(e32/e21)   (fixed point)
    phi_ext = (r21^p phi1 - phi2) / (r21^p - 1)
    GCI21 = 1.25 |e21/phi1| / (r21^p - 1),   GCI32 = 1.25 |e32/phi2| / (r32^p - 1)
    asymptotic range: GCI32 / (r21^p GCI21) ~ 1.

Oscillatory convergence (s < 0) is flagged. With two meshes an assumed order and Fs = 3 are used (`two_mesh`).

### 13.3 Derived fields and node values (`aeroflowsim/post/fields.py`)

Gradients are the solver's weighted least-squares gradients with the boundary condition's face values. Vorticity
omega_z = dv/dx - du/dy; divergence du/dx + dv/dy (+ v/r axisymmetric); numerical schlieren exp(-15 |grad rho| /
max |grad rho|); shock indicator M_n = V . grad p / (c |grad p|) (a shock is where M_n crosses 1; Lovely and Haimes
1999); Cp = (p - p_inf)/q_inf (external) or p/p0 (internal). Node values (smooth contours, streamlines): the
inverse-distance mean of the cells around an interior node; at a boundary node the mean of its boundary-face states
(the mean of the inside cell and the ghost state, i.e. the boundary condition's value). Point values use the cell's
linear reconstruction phi_c + grad phi . (x - x_c); line samples are taken at the ends of each piece of the line
inside one cell, so a plot is exact per cell and shows the jumps between cells.

### 13.4 Integrals and weighting (`aeroflowsim/post/integrals.py`)

Surface element dA = dl (planar, per metre of depth) or 2 pi r dl (axisymmetric, full circle); each segment is
integrated with 2-point Gauss quadrature, exact for a linear field times the linear radius. Area-weighted average
int f dA / int dA; mass-weighted average int f rho |V.n| dA / int rho |V.n| dA (Fluent's convention); mass flow
int rho V.n dA. On a boundary the mass flow and the fluxes are the solver's own numerical boundary fluxes (stored
with every run), so a report equals the solver's balance to round-off. Volume integrals sum cell values times the
cell volume (2 pi times the per-radian volume for axisymmetric meshes). The flux balance sums mass, momentum
(with the pressure force) and energy over every boundary; for axisymmetric meshes the radial momentum is balanced by
the pressure source int p dA, reported separately.

### 13.5 Interpolation onto a new mesh and patch regions

When the mesh has changed, a run starts from the old solution moved to the new cell centres by Shepard
inverse-distance weighting of the 4 nearest old centres (scipy cKDTree): phi_new = sum w_k phi_k / sum w_k,
w_k = 1/d_k. Measured on the N2 nozzle (30 x 6 -> 60 x 12): 4,712 iterations instead of 5,087 from the quasi-1D
start, same mass flow to 4e-6 relative. The gain is modest because the residual is normalised by its first
iterations, which are already small for a good initial solution (gap register). Patch regions replace p, T, u, v in
the cells whose centroid lies in a box, circle or polygon, on top of the Initial solution of a fresh start.

### 13.6 Theory of the new validation cases (`aeroflowsim/gasdynamics.py`)

- Oblique shock: theta-beta-M relation tan(theta) = 2 cot(beta) (M1² sin²beta - 1) / (M1² (gamma + cos 2beta) + 2),
  weak root; normal-shock relations with Mn1 = M1 sin(beta) (Anderson 2003, ch. 4).
- Prandtl-Meyer: nu(M) = sqrt((g+1)/(g-1)) atan(sqrt((g-1)/(g+1) (M²-1))) - atan(sqrt(M²-1)); after a turn
  theta, nu(M2) = nu(M1) + theta; isentropic pressure ratio.
- Shock-expansion theory of the diamond airfoil: oblique shock (or expansion) at the leading edge, Prandtl-Meyer
  expansion at the shoulder on each surface; forces from the four face pressures.
- Taylor-Maccoll: behind a conical shock the flow depends on the polar angle only;
  (g-1)/2 (1 - Vr² - Vt²)(2 Vr + Vt cot(theta) + dVt/dtheta) - Vt (Vr Vt + Vt dVt/dtheta) = 0 with Vt = dVr/dtheta
  (velocities over V_max), integrated from the shock (oblique-shock state) to the cone surface where Vt = 0; the shock
  angle is found by root finding (weak branch). Checked against Sims (1964, NASA SP-3004) to 7e-5 in Cp.

### 13.7 Carbuncle metric

The cylinder validation records, as a report-definition monitor, the volume-weighted pressure in a box around the
stagnation region that contains the bow shock. The metric is its peak-to-peak change over the last 1,000 iterations
divided by its mean: a settled shock gives a tiny value, a carbuncle (a shock that keeps moving) a large one. It
separates the HLLE-blend on / off runs by orders of magnitude, unlike the earlier spatial shock-roughness measure.

### 13.8 Flow animation frames (`aeroflowsim/post/animation.py`)

A frame is the primitive state W = (rho, u, v, p) of every cell at one iteration n, stored in single precision
(relative rounding 6e-8, far below what a colour map shows; frames are never used for numbers). Every other field of
a frame (M, T, p0, Cp, schlieren, custom fields) is computed from W exactly as for the final result. For a steady run
the iteration counter is pseudo-time: the frames show the path of the iterative method (local time steps, the
implicit LU-SGS CFL ramp) from the initial state to the steady state, not a physical transient; only a time-accurate
run (one global dt) shows the real time evolution t^n = sum dt.

Automatic spacing: the number of iterations N is unknown in advance (a steady run stops when it converges), so frames
are kept at n = 0 and every k-th iteration, k = 1 at first; when more than F = 100 frames are stored, every second one
is dropped and k doubles (k = 1, 2, 4, ...). At the end k = 2^m with N / k <= F < 2N / k, so 50 to 100 frames are
evenly spread over any run, at a memory cost of at most F x 4 x 4 bytes per cell. The final state is always the
last frame. When the solver restores its last good state after an unphysical step (CFL back-off), the frames after
that iteration are dropped with it, so the frames always show the path the accepted solution took. Recording only
copies a state the solver has already computed, so it cannot change the result (`tests/test_animation.py` checks
this bit for bit).

## 13b. Compiled kernels, parallel face sums and determinism (Prompt 8-1)

**What changed and what did not.** The equations of section 12 are unchanged. The residual
`R_i = -(1/V_i) [ sum_f s_if F(W_L, W_R; n_f) A_f - p_i G_i - S_i ]` (s_if = +1 if cell i owns face f, -1 if it is
its neighbour) is now evaluated by compiled loops (`aeroflowsim/euler/kernels.py`, Numba) instead of whole-array
NumPy formulas. The NumPy code stays as the reference implementation (`aeroflowsim/compute.py`, backend "numpy");
the tests (`tests/test_kernels.py`) require the two to agree to 1e-12 relative per residual evaluation on every mesh
type, order, limiter and with the carbuncle blend. The kernels are, in order of one evaluation:
`primitive` (U -> W), `gradients` (least squares or Green-Gauss, per cell: grad_i = sum_s a_s X_other(s) + b_i W_i),
`limiter` (Barth-Jespersen / Venkatakrishnan, min over the faces), `reconstruct` (W_L, W_R = W + psi grad . r_f),
`shock_weight` (pressure-jump sensor), `fluxes` (HLLC / HLLE blend, positivity fallback) and `face_sums`;
`time_steps` gives dt_i = CFL V_i / Lambda_i. Ghost states stay in NumPy (boundary faces only).

**Why faster.** NumPy runs each of ~40 formulas over the whole mesh in turn, writing ~40 temporary arrays to memory;
a loop does all formulas for one face while its numbers are in the CPU cache. Measured (validation/timing.md): 9-17 x
on one core, 31-70 x with 16 threads.

**Parallel face sums without races (gather).** A face's flux belongs to two cells. Adding it to both from the face
loop ("scatter") in parallel would let two threads write the same cell at once (a race); atomic additions fix that,
but then the order of additions depends on thread timing, so the last bits of R differ from run to run. Instead
each cell sums its own faces ("gather", the per-cell slot lists of `euler/geometry.py`): every number is computed by
exactly one thread in a fixed order. So a run is bit-for-bit identical for any thread count (tested with exact
array equality); the flux of each face is computed once and read twice.

**Floating-point differences from NumPy.** Sums are done in another order (e.g. the least-squares gradient sums
c_s X_s + b_i X_i with b_i = -sum c_s per cell), so results differ in the last 1-3 digits: relative differences per
residual evaluation are about 1e-15 to 1e-13, and whole runs agree to about 1e-10.

**GPU-ready rule.** Each kernel is a pure function of flat arrays with preallocated outputs, no Python objects and
no global state, and each loop iteration writes only its own cell or face: the same kernels can be ported to CUDA
(one thread per cell or face) later without changing the data layout.

References: Lam, Pitrou & Seibert (2015), "Numba: a LLVM-based Python JIT compiler", LLVM-HPC'15; Blazek (2015),
Computational Fluid Dynamics: Principles and Applications, ch. 5 (face-based data structures).

## 13c. Implicit time stepping: LU-SGS (Prompt 8-2)

**Why.** An explicit scheme may only move information about one cell per stage (CFL < ~1), so a steady flow on a
fine mesh needs tens of thousands of iterations. An implicit scheme solves for the change of the whole field at
once and can take time steps hundreds of times larger.

**The equations.** Backward Euler in time, linearised, for cell i (Blazek 2015, sec. 6.2; Yoon & Jameson 1988):

    (V_i / dt_i) dU_i + sum_f d(F_f A_f) = V_i dU_i/dt |_explicit         (right-hand side: the full residual)

The right-hand side is the SAME second-order residual as the explicit schemes, so the converged solution is
unchanged; only the left-hand side (how fast we get there) is approximated, by the first-order Rusanov
(scalar-dissipation) flux  F_f = 1/2 (F_i + F_j) . n - 1/2 lambda_f (U_j - U_i),  lambda_f = |u . n| + c. Its change
splits into a diagonal part and neighbour parts:

    D_i dU_i + 1/2 sum_{j} A_f [dF_n(U_j; dU_j) - omega lambda_f dU_j] = V_i R_i
    D_i = V_i / dt_i + omega/2 sum_f lambda_f A_f + omega c_i |G_i|

LU-SGS ("lower-upper symmetric Gauss-Seidel") solves this with one sweep forward and one backward through the
cells, without storing any matrix:

    forward  (i = 1..N):   dU*_i = [V_i R_i - 1/2 sum_{j<i} A_f (dF_n(U_j; dU*_j) - omega lambda_f dU*_j)] / D_i
    backward (i = N..1):   dU_i  = dU*_i - [1/2 sum_{j>i} A_f (dF_n(U_j; dU_j) - omega lambda_f dU_j)] / D_i

with dF_n(U_j; dU_j) = F_n(U_j + dU_j) - F_n(U_j) evaluated exactly (no flux Jacobian matrices). Code:
`aeroflowsim/euler/kernels.py` (`lusgs`), called by `EulerSolver._lusgs` (`solver.py`).

**Choices, and why** (each found necessary on the N2 nozzle; the planar MMS and the wedge did not need them):
- omega = 1.5 (Blazek recommends 1 to 2): with omega = 1 the first-order operator does not damp every error of the
  second-order residual, and the nozzle residual stalled near 1e-2; first order converged at once.
- The axisymmetric pressure source p G_i (section 12) enters the diagonal through its spectral radius c_i |G_i|.
  Next to the axis G_i (the planar cell area) is large compared with the r-weighted face areas, and an explicit
  source with large time steps went unphysical there.
- Boundary faces add to the diagonal only (their ghost state depends on the cell inside); the subsonic inlet and
  outlet are therefore treated explicitly, which slows the nozzle's convergence (an implicit boundary Jacobian is a
  later improvement, gap register).
- CFL ramp by switched evolution relaxation (SER, Mulder & van Leer 1985): CFL = CFL_0 / (normalised residual),
  between the input CFL (0.8) and `cfl_max` = 100. It follows the residual down AND up: a ramp that ignored rises
  kept a 96-CFL step after the nozzle start-up transient and never recovered. After an unphysical step the state is
  restored and the whole ramp is halved (as the explicit CFL back-off).
- Deterministic: the sweeps are sequential in the fixed cell order (Gauss-Seidel is sequential by nature); the
  residual runs in parallel. A multi-colour sweep would parallelise them but changes the convergence path with the
  colouring; the sweeps are about a third of the cost of one iteration.
- Limiter chatter: big steps amplify tiny limiter changes, so for implicit runs the stall rule freezes the limiter
  after 2 orders and 200 iterations without a new lowest residual (explicit: 3 orders, 1,000 iterations).

References: Yoon, S. & Jameson, A. (1988), "Lower-upper symmetric-Gauss-Seidel method for the Euler and Navier-Stokes
equations", AIAA J. 26(9), 1025-1026; Blazek (2015), sec. 6.2.4; Mulder, W. A. & van Leer, B. (1985), "Experiments
with implicit upwind methods for the Euler equations", J. Comput. Phys. 59, 232-246.

## 13d. Limiter and order of accuracy (Prompt 8-2)

With the Venkatakrishnan limiter ACTIVE (not frozen, not off), the MMS order depends on K
(`tools/limiter_order.py`, LU-SGS, residual drop 8, L2 error of p; eps² = (K h / L_ref)³ size² with the LOCAL cell
size h, as section 12 requires):

| Mesh | K | order 16-32 | 32-64 | 64-128 |
|---|---:|---:|---:|---:|
| quads | 1 | 1.71 | 1.68 | 1.72 |
| quads | 5 | 1.89 | 1.67 | 1.58 |
| quads | 20 | 2.01 | 2.01 | 2.00 |
| triangles | 1 | 1.23 | 1.03 | 0.91 |
| triangles | 5 | 1.78 | 1.08 | 0.71 |
| triangles | 20 | 2.02 | 2.02 | 1.99 |

Why: eps² ~ h³ shrinks faster than the squared jump between neighbours (~h²) near smooth extrema, so as the mesh is
refined the limiter switches on in more and more smooth cells (clipping extrema = first order there). A larger K
moves that point to finer meshes. Decision: the default stays K = 5. With K = 20 the quick validation set passes as well,
but the peak overshoot at the Mach 2 wedge shock grows from 4.5 % to 5.7 % above p2/p1, so K = 20 is recommended
(help text) for smooth flows only. The accuracy-preserving modification of Michalak & Ollivier-Gooch (2009), which
switches the limiter off only where the solution is smooth, would remove the trade-off: gap register.
Reference: Michalak, C. & Ollivier-Gooch, C. (2009), "Accuracy preserving limiter for the high-order accurate solution
of the Euler equations", J. Comput. Phys. 228, 8693-8711.

## 14. New shapes, nozzle contours and intakes (Prompt 6e, part 1)

Code: `aeroflowsim/shapes/` (one `.toml` + `.py` per shape), `aeroflowsim/nozzle_contours.py`,
`aeroflowsim/intake_theory.py`. Tests: `tests/test_shapes_new.py` (each shape against its defining equation).

**Nose cones of revolution** (`nose_cone.py`; x from the tip, L length, R base radius, y radius):

- Haack series: θ = arccos(1 − 2x/L), y = R √[(θ − sin 2θ / 2 + C sin³θ) / π]. C = 0 is the von Kármán
  (LD-Haack) nose, C = 1/3 the LV-Haack nose (Crowell 1996). At mid-length θ = π/2, so the von Kármán radius is
  exactly R/√2 (tested).
- Ogives: the profile is a circular arc through the tip (0,0) and the base edge (L,R). Tangent ogive: radius
  ρ_t = (R² + L²)/(2R), y = √(ρ_t² − (L − x)²) + R − ρ_t, tangent to the cylinder at the base. Secant ogive: a
  larger radius ρ = k ρ_t (k > 1), the arc cuts the cylinder at an angle (the circle's radius is recovered by a
  least-squares circle fit in the test).
- Power series y = R (x/L)ⁿ; parabolic series y = R (2x/L − K (x/L)²)/(2 − K); ellipse y = R √(1 − ((L − x)/L)²).
- **Spherical blunting.** A sphere of radius r_n with its centre on the axis touches the profile at x_t where the
  normal to the profile passes through the centre. With slope y′ the normal meets the axis at x_t + y y′, and the
  radius is y √(1 + y′²). So x_t solves y(x_t) √(1 + y′(x_t)²) = r_n (a root find); the profile in front of x_t is
  replaced by the sphere. The blunt body is shorter than the sharp profile.

**Blunt bodies.** Sphere; hemisphere-cylinder; spherically blunted cone (sphere tangent to a cone of half-angle θ:
centre x_c = r_n / sin θ, tangent point (x_c − r_n sin θ, r_n cos θ)); sphere-cone capsule: a spherical forebody
(radius R_n), a shoulder arc (radius r_s) tangent to it from inside, and a conical afterbody (half-angle θ_c)
tangent to the shoulder. Tangency from inside needs the shoulder centre at distance R_n − r_s from the sphere
centre and at height R_b − r_s, which gives sin α = (R_b − r_s)/(R_n − r_s) for the polar angle α of the tangent point.

**Biconvex airfoil.** Two circular arcs through the edges, sagitta s = tc/2, half-chord a = c/2, radius
R = (a² + s²)/(2s); area = 2 R² (Θ − sin Θ cos Θ) with sin Θ = a/R (tested to 1e-6).

**NACA 5-digit airfoils** (`naca5.py`): digits LPSTT, design lift coefficient 0.15 L, standard (S = 0) or reflex
(S = 1) camber line with the constants r, k₁ (and k₂/k₁) of the table (Abbott and von Doenhoff 1959; values as
printed on Wikipedia, "NACA airfoil", for c_li = 0.3). Standard: y_c = k₁/6 (x³ − 3r x² + r²(3 − r) x) for x < r,
y_c = k₁ r³/6 (1 − x) after. Reflex: y_c = k₁/6 [(x − r)³ − (k₂/k₁)(1 − r)³ x − r³ x + r³] for x < r and
k₁/6 [(k₂/k₁)(x − r)³ − …] after. For another L the camber is linear in k₁, so k₁ is scaled by L/2. The thickness is
the 4-digit distribution put on perpendicular to the camber line. **Independent check** (thin-airfoil theory): the
ideal lift of a camber line is c_li = 2 ∫₀^π (dy_c/dx) cos θ dθ with x = (1 − cos θ)/2; the tabulated lines give
0.3000 to 0.3001 (230, 240, 250), 0.302 (220), 0.308 (210: the printed r = 0.0580 has only three digits and the
line is very sensitive to it), 0.301-0.305 (reflex), and 0.4501 for L = 3. The peak of the standard camber line is at
x = 0.05 P to 2e-4.

**Rao bell nozzle** (`nozzle_contours.bell_nozzle`). Throat radius R_t, two throat arcs (upstream radius
1.5 R_t, downstream radius 0.382 R_t), then a parabola from point N (wall angle θ_n at the end of the downstream arc)
to the exit E (angle θ_e). The parabola is written as a quadratic Bézier curve with P₀ = N, P₂ = E and control point
P₁ at the crossing of the tangent at N and the tangent at E; it leaves N with slope tan θ_n and arrives at E with
slope tan θ_e. The length is L = L_f R_t (√ε − 1)/tan 15° (L_f: fraction of a 15° cone, typically 0.75-0.85).
θ_n and θ_e come from Huzel and Huang's chart (plot 4-16); the chart was digitised by D. Sd (pygasflow, plot-4-16-data) and
every second point is stored in `RAO_THETA_N` / `RAO_THETA_E` (L_f 0.6 to 1.0, ε 5.2 to 50.3). **These are chart
readings, good to about ±0.5°**; outside the range the user types the angles. The throat-arc radii are from the
Georgia Tech AE 6450 lecture notes (Seitzman), the chart reference length from Huzel and Huang.

**Minimum-length nozzle by the Method of Characteristics** (`nozzle_contours.moc_min_length_nozzle`; Anderson,
*Modern Compressible Flow*, ch. 11). A sharp-corner sonic throat turns the flow by θ_max = ν(M_e)/2 in a centred
expansion fan; the wall then straightens it. Along a left-running characteristic C⁻ (slope θ − μ) the quantity
K⁻ = θ + ν is constant, along a right-running one C⁺ (slope θ + μ) K⁺ = θ − ν. With the fan split into n
characteristics θ_k = kθ_max/n, characteristic number m reflected off the axis has K⁺ = −2θ_m, and C⁻ number k has
K⁻ = 2θ_k, so node (k, m) has θ = θ_k − θ_m and ν = θ_k + θ_m; positions follow from intersecting two straight
characteristic segments with the slopes averaged between their ends. The wall point m is where C⁺ number m, continued
past the last C⁻, reaches the wall, with the wall angle equal to the flow angle there. **Check:** the exit height
ratio y_e/h must equal the isentropic A/A* for the design Mach number; with n = 100 it agrees to 0.2 % (M = 2.4, 3,
γ = 1.4; M = 4, γ = 1.3) and the error falls by a factor of about 2.4 for each doubling of n. Axisymmetric MOC is not
implemented (gap register).

**External-compression intakes** (`intake_theory.py`). Ramp i turns the flow from the angle of ramp i − 1 to δ_i; the
shock angle β from the flow in front comes from the θ-β-M relation tan θ = 2 cot β (M² sin²β − 1) /
(M² (γ + cos 2β) + 2) (Anderson 2003, eq. 4.17); the shock leaves the ramp corner at the absolute angle δ_{i−1} + β.
*Shock on lip*: with one ramp the lip is on the shock line y = x tan ε₁; with two or more it is at the crossing of
shocks 1 and 2, and the miss distance of every other shock from the lip is reported. For a spike (cone) intake the lip
radius is x tan β with the conical-shock angle β from the Taylor-Maccoll solution (`gasdynamics.taylor_maccoll`, the
same code validated against Sims' tables). The rule is a smart rule: shown with its reason and an Apply button, never
automatic. **Limitation:** a ShapeProfile is one closed outline, so the cowl is joined to the centre body by a solid
rear block and the duct is a dead-end pocket; the outlines are for the shock system and the capture, not the duct flow.

### Structured O-grids and C-grids (Prompt 6e, part 2)

Code: `aeroflowsim/structured_mesh.py`; tests: `tests/test_structured_mesh.py`; selected in the Mesh step of
`external_2d` (input *Mesh type*). The grids are made in NumPy (not Gmsh transfinite blocks, see the ledger for why):
one block of (i, j) points, quadrilateral cells, patches named `wall`, `farfield`, `symmetry` / `axis` exactly as in
the unstructured mesh.

**One grid line.** For every i there is a wall point **P** (with unit wall normal **n**, fluid on the left of the
direction of travel, n = (−t_y, t_x)) and a far-field point **Q**. With D = |**Q** − **P**| and **e** = (**Q** − **P**)/D
the point j of the line is

  X_ij = P_i + D s_j u_ij,    u = (1 − w) n + w e, normalised,    w = s^0.7,

with s_j a geometric series: s_1 D = h₀ is the first layer height *exactly*, and the ratio r makes n layers end exactly on
**Q**, h₀ (rⁿ − 1)/(r − 1) = D (solved per line by bisection). The line leaves the wall at a right angle (w ≈ 0) and bends
towards **Q** (w → 1). The ratio is a result, checked against the largest growth rate the user accepts. Tested: first
layer height exact; halving it halves the first cell; halving or doubling the cells around the body, normal to the wall or
in the wake changes the cell count by exactly that factor.

**O-grid** (cylinder, sphere, smooth closed bodies): **P** are the outline points resampled by arc length, **Q** the radial
projection of **P** onto a circle of radius R about the body centre. Half domain: the lines at the two axis points lie on y = 0.
Orthogonality at the wall is exact (below 1e-3 degrees in the tests) on the cylinder.

**C-grid** (airfoils with a sharp trailing edge and a smooth outline): the inner line is the lower wake (outflow to the
trailing edge), the lower surface, the upper surface and the upper wake. The surface points are placed by arc length with
80 % cosine and 20 % uniform spacing (dense at both edges, not extreme); the wake points are a geometric series that starts
with the last surface cell. The far field is a semicircle of radius R about the trailing edge, closed by two horizontal lines
at ±R and the outflow side at x_TE + R. The matching far-field points are placed by the same fractions, partly evened out
("fan" 0.5), so the lines in the wake spread out. The wake line is a cut: its two copies are the same nodes, so the cells above
and below share the faces. Near the trailing edge the surface normals of a wedge point backwards and the lines would cross the
vertical wake lines; the normals are turned to the wake direction over the last half chord (linear weight). Tested on
NACA 0012, 4412, 23012 and a biconvex airfoil at three sizes: no negative cell, skewness 0.38 to 0.49 (0.87 at the sharp
leading edge of the biconvex section).

**Not covered:** blunt trailing edges (a base block is needed), surfaces with interior corners (the resampling would cut
them), edited workspace geometry. The message says why. See the gap register.

### Mesh import and export (Prompt 6e, part 3)

Code: `aeroflowsim/mesh_io.py`; tests: `tests/test_mesh_io.py` (sample files in `tests/data/`); template `cases/imported_mesh`;
command line `mesh-info` and `mesh-convert`.

An imported mesh goes through a neutral `RawMesh` (points, cells, named groups of boundary edges) so that a GUI or script can look at the file
before building anything. `mesh_from_raw` then (1) converts the unit to metres, (2) turns every cell counter-clockwise (shoelace sign),
(3) finds the boundary edges as the cell edges that occur exactly once, (4) checks that every one of them carries a tag (tagged edges that are
not on the boundary, such as an internal zone, are ignored; untagged boundary edges are an error that names the tags found), (5) gives each tag a
boundary type (the user's map, else a guess from the name), (6) drops points no cell uses, and (7) builds the face-based Mesh. 3D files,
elements other than triangles and quadrilaterals, and axisymmetric meshes with y < 0 are refused with a message.

Formats: Gmsh `.msh` 2 and 4 (ASCII and binary) are read with meshio, which reads them correctly, including physical names. The other readers and all writers are our
own because meshio 5.3.5 cannot write tagged 2D meshes: its Gmsh 4 writer needs entity data, its SU2 writer raises an error, and the CGNS file it
writes cannot be read back. SU2: `NELEM`, `NPOIN`, `MARKER_TAG` / `MARKER_ELEMS` (line elements, type 3). Fluent ASCII 2D: sections 10 (nodes), 12 (cells),
13 (faces with their two cells; zone type 2 is interior, 3 a wall: the only type numbers used, as a hint) and 45 (zone names); the corners of each cell
are found by chaining its faces. CGNS: HDF5 nodes with `name`, `label` and `type` attributes and the data in a dataset ` data`; one unstructured
zone, TRI_3 / QUAD_4 / MIXED sections, BAR_2 sections or ZoneBC `PointRange` / `PointList` groups as the boundary tags. Export: a boundary edge group per
patch (Gmsh physical group, SU2 marker, CGNS BAR_2 section plus ZoneBC), written with `repr` of the floats, so importing the file again gives
the same nodes to the last digit, the same cells and the same patches (tested for all four writers, planar, axisymmetric, structured and Gmsh triangle meshes).
The CGNS writer was checked only by our own reader (no CGNS library was available): open an exported file in your other program once before relying on it.

## 15. The optional assistant: it assists, it never replaces physics

**What it is.** A way to fill the Setup inputs from a plain-English description ("Mach 2.4 nitrogen over a 10 degree
wedge, 300 bar chamber pressure, 5 bar back pressure"). Code: `aeroflowsim/assistant/` (the Setup panel is
`aeroflowsim/gui/assistant_panel.py`, the command is `python -m aeroflowsim assist`).

**The principle (CLAUDE.md, "Intelligence").** Intelligence assists, never replaces physics. The assistant is a
*typing aid*: it turns words into numbers in the boxes you could have typed into yourself. It never runs a solver, never
touches results, files or settings, and never decides a physical value. Everything it proposes is then judged by the same
things that judge a typed value: the range and unit in `schema.toml`, and after the run the validity checks.

**The pipeline.** A description goes through five steps, and only the last one changes anything:

1. *Provider* (`rules.py`, `local.py`, `online.py`) turns the text into a list of proposals
   $(\text{field}, \text{value}, \text{unit}, \text{reason})$. A provider is **untrusted**: its answer must be strict JSON
   (`proposal.py`); anything else is discarded as a whole.
2. *Schema review* (`review.py`) checks each proposal like a typed value: the input exists and is one the assistant may
   touch (never a file or the boundary table); the unit belongs to the input's quantity and is converted,
   $x_{\text{input}} = u_{\text{to SI}}(x_{\text{typed}})$ with the same unit table as the GUI (`units.py`;
   bar $\to$ Pa is $\times 10^5$, $^\circ$C $\to$ K is $+273.15$); the value lies in $[\min,\max]$; the input is shown
   with the current choices (`show_if`), counting the other proposals.
3. *Traceability*, for a language model only: the number must be one the user wrote, read in some unit of the input's
   quantity ($|x - u(n)| \le 10^{-6}|x|$ for a number $n$ in the text). A model may therefore not supply a number "from
   memory". Fields that are gas properties ($\gamma$, viscosity, $c_p$, ...) are refused for a model.
4. *Review table*: field, current value, proposed value, unit, reason; one tick box per row.
5. *Apply*: the ticked rows are checked once more against the current values and applied as **one** undo step.

**How the rules provider reads a sentence.** Each number (with its unit, if it has one) is matched to the input whose
*label words* stand next to it. For a number $i$ and an input $f$ with label tokens $T_f$ (from `label` and `key` in
`schema.toml`), and the words $W_i$ within four words on either side (stopping at punctuation, "and" or "with"):

$$
s(i,f) = \sum_{t \in T_f \cap W_i} w_t \;-\; 0.05 \sum_{t \in T_f \setminus W_i} w_t ,\qquad
w_t = \begin{cases} 0.4 & t \in \{\text{pressure, temperature, diameter, angle, number, ...}\}\\ 1 & \text{otherwise.}\end{cases}
$$

A pair needs $s \ge 0.8$ and a unit of the input's quantity (a pressure never goes into a temperature). Pairs are taken
greedily from the highest score, each number and each input once. A pressure or a temperature with *no* label words is
placed on the total pressure / temperature (or the static one when the template has no total), and the reason says it
was assumed. A gas name or formula selects the library gas (never typed properties); a choice option named in full
("wedge") selects that option. A number that cannot be placed is reported, never guessed. Because the labels come from
`schema.toml`, a new input or shape is understood without code.

**What it cannot do (on purpose).** It does not choose numerics, meshes or boundary conditions for you, does not
convert a radius to a diameter, does not read "two" as 2, and does not understand a shape named only by a part of
its name. These limits are the price of a rule you can read in one sitting.

**Privacy.** See the table in the user guide: the rules provider never leaves the program, the local provider only talks
to this computer, the online provider sends the description (and the field definitions, never the current values, project
files, geometry or results) over the internet, only after an explicit opt-in. The only network code is `net.py`; the
desktop GUI files contain none (`tests/test_gui_privacy.py`, `tests/test_assistant.py`).

## 16. References

- Abbott, I. H., von Doenhoff, A. E. (1959). *Theory of Wing Sections*. Dover.
- Crowell, G. A. (1996). *The Descriptive Geometry of Nose Cones*. (Source of the nose-cone equations as given on
  Wikipedia, "Nose cone design", and in the AeroSandbox implementation; the Haack form was confirmed in both, 27 Oct 2026.)
- Huzel, D. K., Huang, D. H. (1992). *Modern Engineering for Design of Liquid-Propellant Rocket Engines*. AIAA
  (plot 4-16, Rao nozzle angles; digitised by D. Sd in pygasflow).
- Rao, G. V. R. (1960). Approximation of optimum thrust nozzle contour. *ARS Journal* (the parabola approximation;
  the paper itself was not reachable, the method is taken from the Georgia Tech notes below).
- Seitzman, J. M. *Nozzle geometries*. Georgia Tech AE 6450 lecture notes (throat arc radii 1.5 and 0.382 R_t).
- Anderson, J. D. (2003). *Modern Compressible Flow*, 3rd ed. McGraw-Hill.
- Cengel, Y. A., Boles, M. A. *Thermodynamics: An Engineering Approach*. McGraw-Hill (Table A-1: gas constants).
- Barth, T. J., Jespersen, D. C. (1989). The design and application of upwind schemes on unstructured meshes.
  AIAA Paper 89-0366.
- Billig, F. S. (1967). Shock-wave shapes around spherical- and cylindrical-nosed bodies. *J. Spacecraft
  Rockets* 4(6), 822-823.
- Blazek, J. (2015). *Computational Fluid Dynamics: Principles and Applications*, 3rd ed. Elsevier.
- Einfeldt, B. (1988). On Godunov-type methods for gas dynamics. *SIAM J. Numer. Anal.* 25(2), 294-318.
- Geuzaine, C., Remacle, J.-F. (2009). Gmsh: a 3-D finite element mesh generator with built-in pre- and
  post-processing facilities. *Int. J. Numer. Meth. Engng.* 79(11), 1309-1331.
- Gottlieb, S., Shu, C.-W. (1998). Total variation diminishing Runge-Kutta schemes. *Math. Comp.* 67, 73-85.
- Haynes, W. M. (ed.). *CRC Handbook of Chemistry and Physics*. CRC Press (enthalpy of fusion of N2, about 0.72 kJ/mol).
- Hirsch, C. (2007). *Numerical Computation of Internal and External Flows*, Vol. 1, 2nd ed. Butterworth-Heinemann.
- Jameson, A., Schmidt, W., Turkel, E. (1981). Numerical solution of the Euler equations by finite volume methods
  using Runge-Kutta time-stepping schemes. AIAA Paper 81-1259.
- Lemmon, E. W., McLinden, M. O., Friend, D. G. Thermophysical Properties of Fluid Systems. In *NIST Chemistry WebBook*, NIST Standard Reference Database 69 (Linstrom, P. J., Mallard, W. G., eds.). (The equation of state and transport correlations used for each gas are named in its gas file.)
- Lemmon, E. W., Jacobsen, R. T., Penoncello, S. G., Friend, D. G. (2000). Thermodynamic properties of air and mixtures of nitrogen, argon, and oxygen from 60 to 2000 K at pressures to 2000 MPa. *J. Phys. Chem. Ref. Data* 29, 331-385.
- Malina, F. J. (1940). Characteristics of the rocket motor unit based on the theory of perfect gases. *J. Franklin
  Inst.* 230, 433-454 (divergence factor (1 + cos alpha)/2).
- McBride, B. J., Zehe, M. J., Gordon, S. (2002). *NASA Glenn coefficients for calculating thermodynamic properties of individual species*. NASA TP-2002-211556 (NASA polynomials; the 7-coefficient sets stored are those of GRI-Mech 3.0, Smith et al.).
- Moitzi, M. *ezdxf: a Python package to create and modify DXF documents*, version 1.4 (MIT licence).
- Nishikawa, H., Kitamura, K. (2008). Very simple, carbuncle-free, boundary-layer-resolving, rotated-hybrid
  Riemann solvers. *J. Comput. Phys.* 227, 2560-2581.
- Open Cascade SAS. *Open CASCADE Technology*, version 7.9 (used through Gmsh's OCC interface).
- Moukalled, F., Mangani, L., Darwish, M. (2016). *The Finite Volume Method in Computational Fluid
  Dynamics*. Springer.
- Peng, D.-Y., Robinson, D. B. (1976). A new two-constant equation of state. *Ind. Eng. Chem. Fundam.* 15(1), 59-64.
- Quirk, J. J. (1994). A contribution to the great Riemann solver debate. *Int. J. Numer. Meth. Fluids* 18, 555-574.
- Shu, C.-W., Osher, S. (1988). Efficient implementation of essentially non-oscillatory shock-capturing schemes.
  *J. Comput. Phys.* 77, 439-471.
- Sutton, G. P., Biblarz, O. (2017). *Rocket Propulsion Elements*, 9th ed. Wiley.
- Sutherland, W. (1893). The viscosity of gases and molecular force. *Phil. Mag.* 36, 507-531.
- Toro, E. F. (2009). *Riemann Solvers and Numerical Methods for Fluid Dynamics*, 3rd ed. Springer.
- Toro, E. F., Spruce, M., Speares, W. (1994). Restoration of the contact surface in the HLL-Riemann
  solver. *Shock Waves* 4, 25-34.
- U.S. Standard Atmosphere, 1976. NOAA, NASA, USAF, NASA-TM-X-74335.
- van Leer, B. (1979). Towards the ultimate conservative difference scheme V. A second-order sequel to
  Godunov's method. *J. Comput. Phys.* 32, 101-136.
- Venkatakrishnan, V. (1995). Convergence to steady state solutions of the Euler equations on unstructured grids
  with limiters. *J. Comput. Phys.* 118, 120-130.
- White, F. M. (2006). *Viscous Fluid Flow*, 3rd ed. McGraw-Hill (Sutherland constants, Tables 1-2 and 1-3).
- Celik, I. B., Ghia, U., Roache, P. J., Freitas, C. J., Coleman, H., Raad, P. E. (2008). Procedure for estimation
  and reporting of uncertainty due to discretization in CFD applications. *J. Fluids Eng.* 130, 078001.
- Back, L. H., Massier, P. F., Gier, H. L. (1964). Comparisons of experimental with predicted wall static-pressure
  distributions in conical supersonic nozzles. JPL Technical Report 32-654 (NASA NTRS 19650001801).
- Lovely, D., Haimes, R. (1999). Shock detection from computational fluid dynamics results. AIAA Paper 99-3285.
- Michalak, C., Ollivier-Gooch, C. (2008). Limiters for unstructured higher-order accurate solutions of the Euler
  equations. AIAA Paper 2008-776.
- Roache, P. J. (1998). *Verification and Validation in Computational Science and Engineering*. Hermosa.
- Roy, C. J., Nelson, C. C., Smith, T. M., Ober, C. C. (2004). Verification of Euler/Navier-Stokes codes using the
  method of manufactured solutions. *Int. J. Numer. Meth. Fluids* 44, 599-620.
- Sims, J. L. (1964). Tables for supersonic flow around right circular cones at zero angle of attack. NASA SP-3004.
- Taylor, G. I., Maccoll, J. W. (1933). The air pressure on a cone moving at high speeds. *Proc. R. Soc. A* 139,
  278-311.
- Vassberg, J. C., Jameson, A. (2010). In pursuit of grid convergence for two-dimensional Euler solutions.
  *J. Aircraft* 47(4), 1152-1166.
