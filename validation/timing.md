# Solver timing (Speed stage (Numba))

Measured on the development machine (Intel Core Ultra 9, 24 physical cores, 32 GB, Windows 11) with
`tools/timing.py`: milliseconds per iteration (SSP-RK3, second order, 3 residual evaluations per iteration) over
200 iterations, times the iteration count of the post-processing and alpha release stage validation run = estimated full wall time. Timings vary
by about 10-20 % between repeats (other programs, turbo clock).

## Before: NumPy reference implementation, one core

Backend: numpy, threads: 16, 200 iterations per case.

| Case | Cells | ms / iteration | Iterations (validation run) | Estimated wall time [s] |
|---|---:|---:|---:|---:|
| MMS quads 64 | 4,096 | 9.96 | - | - |
| MMS quads 128 | 16,384 | 70.12 | 20,367 | 1428 |
| MMS triangles 64 | 8,192 | 26.31 | - | - |
| MMS triangles 128 | 32,768 | 110.90 | 29,216 | 3240 |
| N2 nozzle Coarse | 2,000 | 10.89 | 8,095 | 88 |
| N2 nozzle Medium | 8,000 | 58.36 | 24,688 | 1441 |
| N2 nozzle Fine | 32,000 | 359.16 | - | - |
| N2 nozzle triangles 0.04 | 5,505 | 33.24 | 30,000 | 997 |
| wedge 0.02 L | 3,553 | 19.57 | 1,935 | 38 |
| cylinder polar 60 x 80 | 4,800 | 26.24 | 6,184 | 162 |
| diamond 0.01 c alpha 0 | 10,034 | 59.51 | 1,358 | 81 |
| NACA 0012 0.01 c M 0.8 | 9,400 | 58.67 | 12,771 | 749 |
| NACA 0012 C-grid Medium | 15,600 | 103.90 | - | - |

Profile of one residual evaluation (NumPy reference path, MMS 128 x 128 quads, 16,384 cells, Venkatakrishnan limiter), mean of 50:

| Part | ms | Share |
|---|---:|---:|
| state conversion | 0.21 | 0 % |
| ghost states | 0.03 | 0 % |
| gradients | 0.76 | 2 % |
| limiter | 24.35 | 55 % |
| reconstruction | 4.89 | 11 % |
| flux | 12.18 | 27 % |
| face sums | 0.68 | 2 % |
| time steps | 1.40 | 3 % |
| total | 44.49 | 100 % |

## After: Numba kernels, ONE thread

Backend: numba, threads: 1, 200 iterations per case.

| Case | Cells | ms / iteration | Iterations (validation run) | Estimated wall time [s] |
|---|---:|---:|---:|---:|
| MMS quads 64 | 4,096 | 2.63 | - | - |
| MMS quads 128 | 16,384 | 7.95 | 20,367 | 162 |
| MMS triangles 64 | 8,192 | 2.70 | - | - |
| MMS triangles 128 | 32,768 | 12.45 | 29,216 | 364 |
| N2 nozzle Coarse | 2,000 | 1.62 | 8,095 | 13 |
| N2 nozzle Medium | 8,000 | 5.32 | 24,688 | 131 |
| N2 nozzle Fine | 32,000 | 21.18 | - | - |
| N2 nozzle triangles 0.04 | 5,505 | 3.64 | 30,000 | 109 |
| wedge 0.02 L | 3,553 | 2.45 | 1,935 | 5 |
| cylinder polar 60 x 80 | 4,800 | 3.46 | 6,184 | 21 |
| diamond 0.01 c alpha 0 | 10,034 | 6.28 | 1,358 | 9 |
| NACA 0012 0.01 c M 0.8 | 9,400 | 5.73 | 12,771 | 73 |
| NACA 0012 C-grid Medium | 15,600 | 9.98 | - | - |

## After: Numba kernels, default thread count (physical cores - 1, at most 16 = 16 here)

Backend: numba, threads: 16, 200 iterations per case.

| Case | Cells | ms / iteration | Iterations (validation run) | Estimated wall time [s] |
|---|---:|---:|---:|---:|
| MMS quads 128 | 16,384 | 2.23 | 20,367 | 45 |
| MMS triangles 128 | 32,768 | 2.94 | 29,216 | 86 |
| N2 nozzle Medium | 8,000 | 1.66 | 24,688 | 41 |
| N2 nozzle Fine | 32,000 | 5.10 | - | - |
| NACA 0012 C-grid Medium | 15,600 | 2.90 | - | - |

## Speed-up versus threads

Numba backend, ms per iteration (SSP-RK3, three residuals per iteration):

| Mesh | Cells | 1 thr. [ms] | 2 thr. [ms] | 4 thr. [ms] | 8 thr. [ms] | 16 thr. [ms] | 24 thr. [ms] | speed-up at 24 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MMS quads 64 | 4,096 | 3.26 | 1.39 | 0.65 | 0.69 | 0.66 | 0.66 | 5.0 x |
| MMS quads 128 | 16,384 | 11.47 | 4.32 | 2.46 | 1.76 | 1.84 | 1.27 | 9.0 x |
| MMS quads 256 | 65,536 | 44.30 | 18.70 | 11.47 | 10.31 | 8.13 | 6.54 | 6.8 x |

## Summary

| Mesh | NumPy [ms/it] | Numba 1 thread | Numba 16 threads | Speed-up 1 thread | Speed-up 16 threads |
|---|---:|---:|---:|---:|---:|
| MMS quads 128 (16k cells) | 70.1 | 7.95 | 2.23 | 8.8 x | 31 x |
| MMS triangles 128 (33k cells) | 110.9 | 12.45 | 2.94 | 8.9 x | 38 x |
| N2 nozzle Medium (8k cells) | 58.4 | 5.32 | 1.66 | 11 x | 35 x |
| N2 nozzle Fine (32k cells) | 359.2 | 21.18 | 5.10 | 17 x | 70 x |

- One-core target (10 x on the 16k-cell MMS mesh): reached on the nozzle meshes (11-17 x), missed slightly on the MMS
  quads (8.8 x; one earlier repeat gave 6.8 x). Why: the NumPy MMS run uses no limiter (its slowest part, 55 % of a
  limited residual), and its gradient is already a fast SciPy sparse product, so less is left to gain there.
- Threads: speed-up stops growing beyond about 8 threads on 4k-16k cells (the work per thread becomes too small and
  thread start-up dominates) and reaches 6.8 x at 24 threads on 65k cells, where memory bandwidth limits it.
- Validation suite times before / after: see the CHANGELOG entry of the speed stage (Numba) and the ledger.

## Speed stage (LU-SGS): implicit LU-SGS, wall-clock targets (default threads = 16)

| Target | Limit | Measured | Before speed stage |
|---|---:|---:|---:|
| Default N2 nozzle (Medium, 8k cells) converged | 60 s | 20.8 s (13,771 iterations, LU-SGS) | 13-19 min |
| MMS 128 x 128 quads, residual drop 8 | 120 s | 12.5 s (LU-SGS, 3,982 it); explicit 17.5 s (10,747 it) | 1,646 s |
| Quick validation set | 5 min | 5.0 min (LU-SGS default) | ~32 min |
| Full validation suite | 60 min | 39 min (LU-SGS, NACA study now up to 137k cells; explicit after speed (Numba): 16 min with the old 13k-cell NACA meshes) | ~3 h |

Iterations, LU-SGS vs SSP-RK3 (converged, same solution): MMS 32 x 32 triangles 1,212 vs 5,217 (CFL ramp of the
first version; the final SER ramp needs about 2 x fewer than SSP-RK3 on small MMS meshes, 2.7 x on 128 x 128 quads);
Mach 2 wedge 924-988 vs 1,935; N2 nozzle Medium reaches 3e-6 in 8,000 vs 24,688 to 1e-6.

## 3D Euler solver stage (4 Nov 2026, this PC, Numba, all cores)

| Run | Cells | Scheme | Iterations | Wall clock | Result |
|---|---:|---|---:|---:|---|
| N2 nozzle, revolved quarter (validation full) | 128,000 | LU-SGS, least squares | 30,000 max | 1,723 s incl. the 2D run | mass flow / thrust within 0.15 % of 2D |
| N2 nozzle 3D example (STEP, tetrahedra) | 9,234 | LU-SGS, Green-Gauss, K 1 | 10,474 | 34 s | converged 1e-6 |
| Cone 10 deg Mach 2, quarter (validation full) | 30,825 | LU-SGS, Green-Gauss, K 1 | 20,000 | 257 s | NOT converged |
| Sphere Mach 3, quarter (validation full) | 59,998 | LU-SGS, Green-Gauss, K 1 | 133 | 5 s | DIVERGED |
| same, explicit SSP-RK3 | 59,998 | SSP-RK3 | 6,000 | 151 s | not converged |
| 3D MMS 12^3 + 24^3, three cell types | up to 82,944 | LU-SGS | 564-1,551 | 61 s total | converged 1e-8 |

Memory (tracemalloc, LU-SGS run incl. mesh): 3.0 kB per cell (tetrahedra), 4.2 kB per cell (hexahedra): about
4 GB per million cells; the Run memory check uses 4.5 kB per cell.

Target "sphere at Mach 3 on the 126k-cell mesh converged in under 30 min" (addendum rule 9): NOT MET - not a speed
miss but a robustness one: on the 60k quarter mesh the second-order run diverges with LU-SGS and does not converge in
6,000 explicit iterations, so the 126k run was not attempted (see the stage ledger, Part 7). Slice / iso-surface
timing on the 719k mesh (rule 11): not measured this session; a slice touches only the straddling cells
(`post/view3d._straddling`, tested), so its cost grows with the slice, not the volume.

## Robust-second-order stage (5 Nov 2026, this PC, Numba, all cores, external_3d defaults)

| Run | Cells | Iterations | Wall clock | Result |
|---|---:|---:|---:|---|
| Sphere Mach 3 quarter | 59,998 | 20,000 | 635 s | no divergence, residual ~1e-4 (wake), stand-off 0.227 R |
| Sphere Mach 6 quarter | 59,998 | 20,000 | 628 s | no divergence, stand-off 0.152 R |
| Cone 10 deg Mach 2 | 30,825 / 72,150 | 1,221 / 1,014 | 18 / 38 s | converged |
| 30 deg ramp, tetrahedra / hexahedra | 6,144 / 1,024 | 3,108 / 1,230 | 8 / 1 s | converged |
| Cylinder Mach 3, 2D triangles | 11,435 | 20,000 | 52 s | no divergence, residual 1e-3 (wake), Cd settled 0.05 % |

The node-value gradient (CSR kernel) costs about the same per iteration as least squares (sphere 3,000 it: 104 s).
Target "126k sphere converged in under 30 min": not met (the residual criterion is not reached; see the stage ledger).
