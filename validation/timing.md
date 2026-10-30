# Solver timing (Prompt 8-1)

Measured on the development machine (Intel Core Ultra 9, 24 physical cores, 32 GB, Windows 11) with
`tools/timing.py`: milliseconds per iteration (SSP-RK3, second order, 3 residual evaluations per iteration) over
200 iterations, times the iteration count of the Prompt 7b validation run = estimated full wall time. Timings vary
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
- Validation suite times before / after: see the CHANGELOG entry of Prompt 8-1 and the ledger.
