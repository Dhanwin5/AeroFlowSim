# Prompt 7b progress ledger

If the session was summarised or interrupted: re-read this file and `CLAUDE.md`, then continue with "Next".
Order of work (addendum A): Part 6 → Parts 1-2 → Part 7 → Part 3 → Parts 4-5 → Part 8 → Part 9 → Parts 10-11.

## Done

| Part | What | Commit | Verified by |
|---|---|---|---|
| 6 | MMS (`aeroflowsim/mms.py`), solver hooks (source, boundary face values), limiter "None", smooth mesh warp, GCI tool, `validation/mms_euler2d`, quick/full validation sets | 4d355c6 | `tests/test_mms_gci.py`; full study 16-128: L2 order 1.98-2.02 on quads, distorted quads, triangles, mixed, planar + axisymmetric (all PASS) |
| 1-2 | `aeroflowsim/post/` (solution, fields + safe formulas, sampling, surfaces, integrals, flux balance, forces, report definitions + monitors + CSV writer), project settings, run extras (monitors, patches, interpolation) | 4d355c6, c51ff89 | `tests/test_post.py` (29), `tests/test_post_project.py` (8; stop/continue/scratch CSV walk-through, convergence criterion, snapshots, exports, patches; interpolation test marked validation) |
| 4-5 | snapshots, compare, export (CSV/VTU node data/Tecplot), XY data, CLI `report`/`export`/`snapshot` | c51ff89 + later | tests above, `tests/test_report.py` |
| 7 | diamond, cone, Prandtl-Meyer, NACA 0012 (Vassberg & Jameson Table 10/11 fetched), BMG nozzle (JPL TR 32-654 fetched, Fig. 4 digitized), carbuncle metric, rounded throat + GCI in nozzle study, Taylor-Maccoll/shock-expansion/PM theory | d4b1519 + later | quick runs: diamond 7/7 within 0.4 %, PM 0.66 %/0.05 %, cone Cp 0.09 %, BMG 8/9 points (z = 2.24 in SHORTFALL explained) |
| 3 | Results workspace: display scenes, contours/lines/vectors/streamlines/mirror/revolve, 1/2/4 linked views, surfaces by click, reports, XY plot in Plots area, snapshots compare, custom fields, histogram, pictures, right-click, hover; Run start options | d4b1519 | `tests/gui/test_post_gui.py` (7) + all GUI tests (64 pass); screenshots via `tools/screenshots.py` |
| 8 | `post/report.py` HTML + PDF, `post/pictures.py`, CLI report, GUI Tools > Project report | (this commit) | `tests/test_report.py` (3 templates, sections, no web addresses, Qt blocked) |
| 9 | installer (PyInstaller + Inno Setup, per user, .afsproj association via `project.afsproj`, uninstaller), smoke test, THIRD_PARTY_LICENSES.txt, workflows (tests quick set, weekly full validation, installer on tags), user guide, 3 tutorials, theory manual section 13, developer guide, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue templates, parity checklist, examples + start page, diagnostics + log + error dialog, version 0.2.0a1 | (this commit) | first build 166 MB, smoke test passed (version fix after) ; silent install + registry checked |

## Next

1. Fast tests (running), commit.
2. Full validation in the background (`run_all.py --jobs 3`), compare with `report_before.md` (rule 4), update theory-manual MMS table from `last_study.json`.
3. Dark + 150 % screenshots, fix what is ugly.
4. Final installer build + install / double-click / uninstall test; README screenshots, `docs/showcase/`.
5. Gap register, CLAUDE.md layout, `docs/prompts/prompt_8.md` + `next_steps.md`, push, tag, release (only if the gates hold).

## Decisions

- Validation folders whose "case" is not a template use `case = "aeroflowsim/<module>.py"`.
- Quick set writes `validation/report_quick.md`, full set `validation/report.md`; references may have `tolerance_percent_quick` and `shortfall` (status SHORTFALL: shown with its explanation, not counted as failure).
- Mass-weighted average uses rho |V.n| (Fluent). Boundary fluxes in post-processing are the solver's stored final fluxes.
- Cone reference: Sims 1964 (NASA SP-3004, tabulated) instead of the charts of NACA 1135.
- Cone shock located by the maximum density gradient (the half-level method is biased behind a conical shock).
- .afsproj association: every project folder gets a small file `project.afsproj`; double-clicking it opens the folder.
- `run_all.py` runs cases sequentially by default (`--jobs N` parallel).

## Open anomalies

- Diamond airfoil: residual stalls ~4e-3 at the lower leading-edge shock foot (limiter limit cycle); Cl, Cd steady to 1e-6. Prompt 8.
- Venkatakrishnan limiter loses order under refinement on smooth flows (MMS, triangles ~0.7-1.0). Gap register.
- BMG z = 2.24 in: 0.80 vs 0.87 measured, mesh-converged; cause not settled (steep gradient + position uncertainty, tap size). Gap register.
- Interpolated start only ~8 % fewer iterations (residual normalisation by the first iterations). Gap register.
- Two idle Python processes of an earlier parallel validation run could not be stopped (permission); they finished by themselves.
