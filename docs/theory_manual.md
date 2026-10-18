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
10. [References](#10-references)

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

## 9. Geometry: rounded throat and the shape library

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

---

## 10. References

- Abbott, I. H., von Doenhoff, A. E. (1959). *Theory of Wing Sections*. Dover.
- Anderson, J. D. (2003). *Modern Compressible Flow*, 3rd ed. McGraw-Hill.
- Blazek, J. (2015). *Computational Fluid Dynamics: Principles and Applications*, 3rd ed. Elsevier.
- Geuzaine, C., Remacle, J.-F. (2009). Gmsh: a 3-D finite element mesh generator with built-in pre- and
  post-processing facilities. *Int. J. Numer. Meth. Engng.* 79(11), 1309-1331.
- Gottlieb, S., Shu, C.-W. (1998). Total variation diminishing Runge-Kutta schemes. *Math. Comp.* 67, 73-85.
- Moukalled, F., Mangani, L., Darwish, M. (2016). *The Finite Volume Method in Computational Fluid
  Dynamics*. Springer.
- Toro, E. F. (2009). *Riemann Solvers and Numerical Methods for Fluid Dynamics*, 3rd ed. Springer.
- Toro, E. F., Spruce, M., Speares, W. (1994). Restoration of the contact surface in the HLL-Riemann
  solver. *Shock Waves* 4, 25-34.
- van Leer, B. (1979). Towards the ultimate conservative difference scheme V. A second-order sequel to
  Godunov's method. *J. Comput. Phys.* 32, 101-136.
