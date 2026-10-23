# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Developer tool (not part of the package): write the built-in gas files aeroflowsim/gases/<id>.toml.

Every number in those files comes from a named source; this script makes the step from the source
data to the file repeatable. It is run by hand when the gas data changes:

    python tools/gas_data/make_gas_files.py <folder with the NIST tables> [--download]

--download fetches the tables from the NIST Chemistry WebBook (SRD 69, "Thermophysical Properties of
Fluid Systems", https://webbook.nist.gov/chemistry/fluid/) and the GRI-Mech 3.0 thermo file into the
folder first. (Only this developer tool uses the network; AeroFlowSim itself never does.)

What it does per gas:
1. Molar mass and critical point (Tc, pc, acentric factor): typed in below from the NIST WebBook
   pages (each listed with its source).
2. gamma: cp/cv of the NIST table at 300 K and 0.1 kPa (ideal-gas limit), rounded to 4 decimals;
   monatomic gases 5/3 exactly (kinetic theory); N2 keeps the validated 1.4 (see the N2 note).
3. Thermo range: the temperatures around 300 K where NIST cp stays within 1 % of the constant cp.
4. Viscosity and conductivity: Sutherland and power laws are fitted (least squares on the relative
   error) to the NIST values at 0.1 kPa; the law and the widest temperature range around 300 K with
   at most MAX_FIT_ERROR deviation are kept, with the largest deviation written in the file.
5. Prandtl number: mu cp / k of the NIST table at 300 K.
6. Vapour pressure: SAT_POINTS points (evenly spaced in ln p) of the NIST saturation table, from the triple point to the
   critical point (ln p is interpolated in 1/T between them).
7. NASA 7-coefficient polynomials copied from GRI-Mech 3.0 (thermo30.dat) where the gas is in it.
8. A few NIST points (T, cp, cv, mu, k) as [reference] for the tests.
Air is not a NIST pure fluid: its file is written by hand (US Standard Atmosphere 1976).
"""

import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

R_U = 8.314462618               # [J/(mol K)]
MAX_FIT_ERROR = 2.0             # largest accepted deviation of a transport law from the NIST data [%]
CP_TOLERANCE = 2.0              # thermo range: |cp_NIST / cp_constant - 1| below this [%]
T_REF = 273.15                  # reference temperature of the transport laws [K]
SAT_POINTS = 30                 # points of the stored saturation curve [-]
NIST = "NIST Chemistry WebBook, SRD 69, Thermophysical Properties of Fluid Systems (E.W. Lemmon et al.)"
OUT = Path(__file__).resolve().parents[2] / "aeroflowsim" / "gases"
BASE = ("https://webbook.nist.gov/cgi/fluid.cgi?Action=Data&Digits=6&RefState=DEF&TUnit=K&PUnit=bar"
        "&DUnit=kg%2Fm3&HUnit=kJ%2Fkg&WUnit=m%2Fs&VisUnit=uPa*s&STUnit=N%2Fm")

# id: name, formula, NIST id, molar mass [kg/mol], Tc [K], pc [Pa], omega, isobar range and step [K],
#     EOS / transport references (from the NIST page), GRI-Mech name, monatomic, note
GASES = {
    "N2": dict(name="Nitrogen", nist="C7727379", M=0.0280134, Tc=126.192, pc=3.3958e6, w=0.0372, T=(63.151, 1000, 2),
               eos="Span, Lemmon, Jacobsen, Wagner & Yokozeki, J. Phys. Chem. Ref. Data 29 (2000) 1361",
               transport="Lemmon & Jacobsen, Int. J. Thermophys. 25 (2004) 21", gri="N2"),
    "O2": dict(name="Oxygen", nist="C7782447", M=0.0319988, Tc=154.581, pc=5.043e6, w=0.0222, T=(54.361, 1000, 2),
               eos="Schmidt & Wagner, Fluid Phase Equilib. 19 (1985) 175",
               transport="Lemmon & Jacobsen, Int. J. Thermophys. 25 (2004) 21", gri="O2"),
    "Ar": dict(name="Argon", nist="C7440371", M=0.039948, Tc=150.687, pc=4.863e6, w=-0.00219, T=(83.806, 700, 2),
               eos="Tegeler, Span & Wagner, J. Phys. Chem. Ref. Data 28 (1999) 779",
               transport="Lemmon & Jacobsen, Int. J. Thermophys. 25 (2004) 21", gri="AR", monatomic=True),
    "He": dict(name="Helium", nist="C7440597", M=0.004002602, Tc=5.1953, pc=2.2832e5, w=-0.3836, T=(2.5, 1500, 5),
               eos="Ortiz-Vega, Hall, Holste, Arp, Harvey & Lemmon (2018), as implemented in the NIST WebBook",
               transport="Arp, McCarty & Friend, NIST TN 1334 (1998); Hands & Arp, Cryogenics 21 (1981) 697",
               monatomic=True),
    "Kr": dict(name="Krypton", nist="C7439909", M=0.083798, Tc=209.48, pc=5.525e6, w=-0.000894, T=(115.78, 750, 2),
               eos="Lemmon & Span, J. Chem. Eng. Data 51 (2006) 785",
               transport="Huber, NIST IR 8209 (2018)", monatomic=True),
    "Xe": dict(name="Xenon", nist="C7440633", M=0.131293, Tc=289.733, pc=5.842e6, w=0.00363, T=(161.41, 750, 2),
               eos="Lemmon & Span, J. Chem. Eng. Data 51 (2006) 785",
               transport="Huber, NIST IR 8209 (2018)", monatomic=True),
    "CO2": dict(name="Carbon dioxide", nist="C124389", M=0.0440095, Tc=304.1282, pc=7.3773e6, w=0.22394,
                T=(216.592, 1100, 2), eos="Span & Wagner, J. Phys. Chem. Ref. Data 25 (1996) 1509",
                transport="as implemented in the NIST WebBook (see the CO2 fluid page)", gri="CO2"),
    "H2": dict(name="Hydrogen (normal)", nist="C1333740", M=0.00201588, Tc=33.145, pc=1.2964e6, w=-0.219,
               T=(13.957, 1000, 2), eos="Leachman, Jacobsen, Penoncello & Lemmon, J. Phys. Chem. Ref. Data 38 (2009) 721",
               transport="as implemented in the NIST WebBook (see the H2 fluid page)", gri="H2"),
    "H2O": dict(name="Water vapour (steam)", nist="C7732185", M=0.0180153, Tc=647.096, pc=2.2064e7, w=0.3443,
                T=(273.16, 1273, 2), eos="IAPWS-95: Wagner & Pruss, J. Phys. Chem. Ref. Data 31 (2002) 387",
                transport="IAPWS formulations as implemented in the NIST WebBook", gri="H2O"),
    "R236fa": dict(name="R-236fa (1,1,1,3,3,3-hexafluoropropane)", nist="C690391", M=0.1520384, Tc=398.07,
                   pc=3.2e6, w=0.377, T=(179.6, 400, 1),
                   eos="Pan, Rui, Zhao & Qiu, Fluid Phase Equilib. 321 (2012) 10",
                   transport="Huber, NIST IR 8209 (2018)",
                   note=("Ideal-gas values are an APPROXIMATION for R-236fa. They are not valid near saturation "
                         "or at storage conditions (R-236fa is stored as a liquid at its vapour pressure, 2.29 bar "
                         "at 20 C (NIST), where the saturated vapour has Z = 0.918). Use only for dilute, superheated vapour and "
                         "check the ideal-gas validity and condensation checks of every run.")),
}
N2_NOTE = ("gamma = 1.4 and R = 296.8 J/(kg K) are the 4-figure values used by the validated quasi-1D case "
           "(validation/quasi1d_nozzle). NIST gives cp/cv = 1.3995 at 300 K (0.03 % lower) and "
           "R_u / M = 296.803 J/(kg K) (0.001 % higher); both differences are far below every tolerance.")


def download(folder):
    import urllib.request
    folder.mkdir(parents=True, exist_ok=True)
    for gid, g in GASES.items():
        lo, hi, step = g["T"]
        for kind, query in (("isobar", f"&Type=IsoBar&P=0.001&TLow={lo}&THigh={hi}&TInc={step}"),
                            ("sat", f"&Type=SatT&TLow={lo}&THigh={g['Tc'] - 0.05}&TInc={(g['Tc'] - lo) / 400:.4f}")):
            with urllib.request.urlopen(f"{BASE}&ID={g['nist']}{query}", timeout=60) as response:
                (folder / f"{gid}_{kind}.tsv").write_bytes(response.read())
    with urllib.request.urlopen("http://combustion.berkeley.edu/gri-mech/version30/files30/thermo30.dat",
                                timeout=60) as response:
        (folder / "thermo30.dat").write_bytes(response.read())


def table(path, phase="vapor"):
    """NIST tab-separated table -> dict of columns (vapour rows only)."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    head = lines[0].split("\t")
    rows = [line.split("\t") for line in lines[1:] if line.strip()]
    rows = [r for r in rows if r[-1].strip() == phase]
    rows = [r for n, r in enumerate(rows) if n == 0 or r[0] != rows[n - 1][0]]     # saturation tables repeat rows
    number = lambda text: float(text) if text.strip() not in ("undefined", "") else math.nan
    col = lambda name: np.array([number(r[head.index(name)]) for r in rows])
    return {"T": col("Temperature (K)"), "p": col("Pressure (bar)") * 1e5, "cp": col("Cp (J/g*K)") * 1e3,
            "cv": col("Cv (J/g*K)") * 1e3, "mu": col("Viscosity (uPa*s)") * 1e-6, "k": col("Therm. Cond. (W/m*K)")}


def law_value(law, p, T):
    if law == "sutherland":
        return p[0] * (T / T_REF) ** 1.5 * (T_REF + p[1]) / (T + p[1])
    return p[0] * (T / T_REF) ** p[1]


def fit(law, T, y):
    start = [float(np.interp(T_REF, T, y)), 120.0 if law == "sutherland" else 0.7]
    result = least_squares(lambda p: law_value(law, p, T) / y - 1.0, start)
    return result.x, 100.0 * np.abs(result.fun).max()


def best_law(T, y):
    """(law, params, T_min, T_max, max error %) for the widest range around 300 K within MAX_FIT_ERROR."""
    best = None
    i300 = int(np.argmin(np.abs(T - 300.0)))
    starts = list(range(0, i300 - 5, max(1, i300 // 40))) + [max(0, i300 - 5)]
    ends = list(range(len(T) - 1, i300 + 5, -max(1, (len(T) - i300) // 40))) + [min(len(T) - 1, i300 + 5)]
    for law in ("sutherland", "power"):
        for i in starts:
            for j in ends:
                if best is not None and math.log(T[j] / T[i]) <= best[0]:
                    continue                             # cannot beat the widest range found so far
                params, error = fit(law, T[i:j + 1], y[i:j + 1])
                if error <= MAX_FIT_ERROR:
                    best = (math.log(T[j] / T[i]), law, params, T[i], T[j], error)
    _, law, params, lo, hi, error = best
    return law, params, lo, hi, error


def gri_polynomials(path, name):
    lines = path.read_text().splitlines()
    for n, line in enumerate(lines):
        if line[:18].split() and line[:18].split()[0] == name and line.rstrip().endswith("1"):
            T = [float(line[45:55]), float(line[65:75]), float(line[55:65])]          # low, mid, high
            text = "".join(l[:75] for l in lines[n + 1:n + 4])
            numbers = [float(text[15 * k:15 * k + 15]) for k in range(14)]
            return {"T": T, "high": numbers[:7], "low": numbers[7:]}
    return None


def fmt(x, digits=6):
    return f"{x:.{digits}g}"


def write_gas(gid, g, folder):
    iso = table(folder / f"{gid}_isobar.tsv")
    sat = table(folder / f"{gid}_sat.tsv")
    good = np.isfinite(iso["mu"]) & np.isfinite(iso["k"]) & np.isfinite(iso["cp"])
    iso = {key: values[good] for key, values in iso.items()}
    T = iso["T"]
    i300 = int(np.argmin(np.abs(T - 300.0)))
    R = R_U / g["M"]
    if gid == "N2":
        gamma, R_text = 1.4, 296.8
    elif g.get("monatomic"):
        gamma, R_text = 5.0 / 3.0, None
    else:
        gamma, R_text = round(iso["cp"][i300] / iso["cv"][i300], 4), None
    R_used = R_text or R
    cp_const = gamma * R_used / (gamma - 1.0)
    ok = np.abs(iso["cp"] / cp_const - 1.0) * 100.0 <= CP_TOLERANCE
    lo = i300
    while lo > 0 and ok[lo - 1]:
        lo -= 1
    hi = i300
    while hi < len(T) - 1 and ok[hi + 1]:
        hi += 1
    mu_law, mu_p, mu_lo, mu_hi, mu_err = best_law(T, iso["mu"])
    k_law, k_p, k_lo, k_hi, k_err = best_law(T, iso["k"])
    t_lo, t_hi = max(mu_lo, k_lo), min(mu_hi, k_hi)
    prandtl = iso["mu"][i300] * iso["cp"][i300] / iso["k"][i300]
    # saturation curve: ~20 points triple -> critical, plus the critical point itself
    below = sat["T"] < g["Tc"] - 1e-6
    sat = {key: values[below] for key, values in sat.items()}
    lnp = np.log(sat["p"])                                     # points evenly spaced in ln p
    idx = np.unique([int(np.argmin(np.abs(lnp - v))) for v in np.linspace(lnp[0], lnp[-1], SAT_POINTS)])
    Ts, ps = list(sat["T"][idx]), list(sat["p"][idx])
    Ts.append(g["Tc"])
    ps.append(g["pc"])
    def law_text(law, p):
        second = f"S = {fmt(p[1], 5)}" if law == "sutherland" else f"n = {fmt(p[1], 5)}"
        return f'{{ law = "{law}", ref = {fmt(p[0], 6)}, T_ref = {T_REF}, {second} }}'
    ref_T = [t for t in (100, 200, 300, 400, 500, 700, 1000) if T[0] <= t <= T[-1]]
    ref_i = [int(np.argmin(np.abs(T - t))) for t in ref_T]
    out = [f"# {g['name']}: built-in gas of AeroFlowSim, written by tools/gas_data/make_gas_files.py.",
           "# SI units. Every value names its source; the tests compare the laws with the [reference] data.", "",
           f'id = "{gid}"', f'name = "{g["name"]}"', f'formula = "{gid}"', 'model = "calorically perfect"']
    note = N2_NOTE if gid == "N2" else g.get("note", "")
    if note:
        out.append(f'note = "{note}"')
    out += ["", "[constants]", f"molar_mass = {g['M']}   # kg/mol",
            f'molar_mass_source = "NIST Chemistry WebBook, SRD 69 (molecular weight)"']
    if R_text:
        out += [f"R = {R_text}   # J/(kg K), tabulated (R_u / M = {R:.3f})",
                'R_source = "4-figure table value, e.g. Cengel & Boles, Thermodynamics, Table A-1 (0.2968 kJ/(kg K)); kept for the validated quasi-1D case"']
    if g.get("monatomic"):
        out += ["gamma = 1.6666666666666667   # 5/3",
                f'gamma_source = "monatomic ideal gas, cp = 5/2 R (kinetic theory); NIST cp/cv at 300 K = {iso["cp"][i300] / iso["cv"][i300]:.5f}"']
    else:
        out += [f"gamma = {gamma}",
                f'gamma_source = "cp/cv = {iso["cp"][i300] / iso["cv"][i300]:.5f} at 300 K, 0.1 kPa, {NIST}; EOS {g["eos"]}"']
    out += [f"T_min = {fmt(T[lo], 6)}   # K", f"T_max = {fmt(T[hi], 6)}   # K",
            f'T_range_source = "where NIST cp at 0.1 kPa is within {CP_TOLERANCE:g} % of the constant cp = {cp_const:.2f} J/(kg K)'
            + (" (lower end: the triple point / lowest temperature of the EOS)" if lo == 0 else "") + '"', "",
            "[transport]", f"viscosity = {law_text(mu_law, mu_p)}", f"conductivity = {law_text(k_law, k_p)}",
            f"prandtl = {prandtl:.4f}   # mu cp / k at 300 K (NIST)",
            f"T_min = {fmt(t_lo, 6)}   # K", f"T_max = {fmt(t_hi, 6)}   # K",
            f"max_error_percent = {max(mu_err, k_err):.2f}",
            f'source = "laws fitted (least squares, relative error) to {NIST} at 0.1 kPa: viscosity {fmt(mu_lo, 5)}-{fmt(mu_hi, 5)} K '
            f'(max {mu_err:.2f} %), conductivity {fmt(k_lo, 5)}-{fmt(k_hi, 5)} K (max {k_err:.2f} %); transport data {g["transport"]}"', "",
            "[critical]", f"T = {g['Tc']}   # K", f"p = {g['pc']:.6g}   # Pa", f"acentric_factor = {g['w']}",
            f'source = "{NIST}, fluid page (critical point, acentric factor)"', "",
            "[vapour_pressure]", f'source = "saturation table of {NIST}; EOS {g["eos"]}; last point = critical point"',
            "T = [" + ", ".join(fmt(t, 7) for t in Ts) + "]   # K",
            "p = [" + ", ".join(fmt(p, 7) for p in ps) + "]   # Pa"]
    gri = g.get("gri") and gri_polynomials(folder / "thermo30.dat", g["gri"])
    if gri:
        out += ["", "[nasa7]", 'source = "GRI-Mech 3.0, thermo30.dat (Smith et al., combustion.berkeley.edu/gri-mech)"',
                f"T = {gri['T']}   # K: low, middle, high",
                "low = [" + ", ".join(f"{a:.8e}" for a in gri["low"]) + "]",
                "high = [" + ", ".join(f"{a:.8e}" for a in gri["high"]) + "]"]
    out += ["", "[reference]", f'source = "{NIST}, isobar 0.1 kPa"',
            "T = [" + ", ".join(fmt(T[i]) for i in ref_i) + "]   # K",
            "cp = [" + ", ".join(fmt(iso["cp"][i]) for i in ref_i) + "]   # J/(kg K)",
            "cv = [" + ", ".join(fmt(iso["cv"][i]) for i in ref_i) + "]   # J/(kg K)",
            "mu = [" + ", ".join(fmt(iso["mu"][i]) for i in ref_i) + "]   # Pa s",
            "k = [" + ", ".join(fmt(iso["k"][i]) for i in ref_i) + "]   # W/(m K)", ""]
    (OUT / f"{gid}.toml").write_text("\n".join(out), encoding="utf-8")
    # how good is the saturation interpolation? (printed for the developer)
    from aeroflowsim.gases.data import VapourPressure
    curve = VapourPressure(Ts, ps)
    error = np.abs(curve.p_sat(sat["T"]) / sat["p"] - 1.0).max() * 100.0
    print(f"{gid:7s} gamma {gamma:.4f}  thermo {T[lo]:.0f}-{T[hi]:.0f} K  mu {mu_law} {mu_lo:.0f}-{mu_hi:.0f} K "
          f"{mu_err:.2f} %  k {k_law} {k_lo:.0f}-{k_hi:.0f} K {k_err:.2f} %  Pr {prandtl:.3f}  p_sat interp {error:.2f} %")


# Air (US Standard Atmosphere 1976, NOAA/NASA/USAF): composition by volume, molar mass and gas constant,
# and its Sutherland viscosity law; conductivity from White, Viscous Fluid Flow, Table 1-3.
AIR_X = {"N2": 0.78084, "O2": 0.209476, "Ar": 0.00934}    # mole fractions (CO2, 0.000314, left out)
AIR_M, AIR_R = 0.0289644, 287.053                         # [kg/mol], [J/(kg K)] (US Std 1976: R* = 8.31432)
AIR_BETA, AIR_S = 1.458e-6, 110.4                         # mu = beta T^1.5 / (T + S) [kg/(m s K^0.5)], [K]
AIR_K_REF, AIR_K_TREF, AIR_K_S = 0.0241, 273.0, 194.0     # White Table 1-3 [W/(m K)], [K], [K]


def us_std_conductivity(T):
    """k(T) of the US Standard Atmosphere 1976 [W/(m K)] (used only to check White's law)."""
    return 2.64638e-3 * T**1.5 / (T + 245.4 * 10.0 ** (-12.0 / T))


def write_air(folder):
    tables = {g: table(folder / f"{g}_isobar.tsv") for g in AIR_X}
    T = np.arange(64.0, 701.0, 2.0)                           # from the N2 triple point (63.151 K) [K]
    ar = tables["Ar"]                                         # Ar data start at 84 K; below, its ideal-gas
    ar_R = R_U / GASES["Ar"]["M"]                             # cp = 5/2 R and cv = 3/2 R exactly (monatomic)
    for key, factor in (("cp", 2.5), ("cv", 1.5)):
        ar[key] = np.concatenate([[factor * ar_R], ar[key]])
    ar["T"] = np.concatenate([[T[0]], ar["T"]])
    total = sum(AIR_X[g] * GASES[g]["M"] for g in AIR_X)
    w = {g: AIR_X[g] * GASES[g]["M"] / total for g in AIR_X}  # mass fractions
    cp = sum(w[g] * np.interp(T, tables[g]["T"], tables[g]["cp"]) for g in AIR_X)   # ideal mixing
    cv = sum(w[g] * np.interp(T, tables[g]["T"], tables[g]["cv"]) for g in AIR_X)
    i300 = int(np.argmin(np.abs(T - 300.0)))
    cp_const = 1.4 * AIR_R / 0.4
    ok = np.abs(cp / cp_const - 1.0) * 100.0 <= CP_TOLERANCE
    lo = hi = i300
    while lo > 0 and ok[lo - 1]:
        lo -= 1
    while hi < len(T) - 1 and ok[hi + 1]:
        hi += 1
    Tk = np.arange(100.0, 2001.0, 10.0)
    k_white = AIR_K_REF * (Tk / AIR_K_TREF) ** 1.5 * (AIR_K_TREF + AIR_K_S) / (Tk + AIR_K_S)
    dev = np.abs(k_white / us_std_conductivity(Tk) - 1.0) * 100.0
    j300 = int(np.argmin(np.abs(Tk - 300.0)))
    klo = khi = j300
    while klo > 0 and dev[klo - 1] <= MAX_FIT_ERROR:
        klo -= 1
    while khi < len(Tk) - 1 and dev[khi + 1] <= MAX_FIT_ERROR:
        khi += 1
    mu = lambda T: AIR_BETA * T**1.5 / (T + AIR_S)
    mu_ref = mu(T_REF)
    prandtl = mu(300.0) * cp_const / us_std_conductivity(300.0)
    ref_T = [100.0, 200.0, 300.0, 500.0, 1000.0]
    std = "U.S. Standard Atmosphere, 1976 (NOAA, NASA, USAF), NASA-TM-X-74335"
    out = ["# Air: built-in gas of AeroFlowSim, written by tools/gas_data/make_gas_files.py.",
           "# SI units. Every value names its source; the tests compare the laws with the [reference] data.", "",
           'id = "air"', 'name = "Air (dry)"', 'formula = "air"', 'model = "calorically perfect"',
           'note = "Dry air as one ideal gas (no dissociation, no humidity). No condensation data: air is a mixture '
           'with a dew line, not one saturation curve; the condensation check does not apply."', "",
           "[constants]", f"molar_mass = {AIR_M}   # kg/mol", f'molar_mass_source = "{std}, sea-level mean molecular weight"',
           f"R = {AIR_R}   # J/(kg K)", f'R_source = "{std} (R* = 8.31432 J/(mol K)); R_u / M with CODATA 2018 R_u = {R_U / AIR_M:.3f}"',
           "gamma = 1.4", f'gamma_source = "{std}; ideal mixing of NIST N2, O2, Ar data gives cp/cv = {cp[i300] / cv[i300]:.5f} at 300 K"',
           f"T_min = {T[lo]:g}   # K", f"T_max = {T[hi]:g}   # K",
           f'T_range_source = "where the ideal mixture of NIST N2, O2 and Ar (0.1 kPa, US Std 1976 mole fractions) has cp within '
           f'{CP_TOLERANCE:g} % of the constant cp = {cp_const:.2f} J/(kg K); Ar below 84 K: cp = 5/2 R (monatomic)'
           + (' (lower end: the N2 triple point)' if lo == 0 else '') + '"', "",
           "[transport]", f'viscosity = {{ law = "sutherland", ref = {mu_ref:.7g}, T_ref = {T_REF}, S = {AIR_S} }}',
           f'conductivity = {{ law = "sutherland", ref = {AIR_K_REF}, T_ref = {AIR_K_TREF}, S = {AIR_K_S} }}',
           f"prandtl = {prandtl:.4f}   # mu cp / k at 300 K (US Std 1976 laws)",
           f"T_min = {Tk[klo]:g}   # K", f"T_max = {Tk[khi]:g}   # K",
           f"max_error_percent = {dev[klo:khi + 1].max():.2f}",
           f'source = "viscosity: Sutherland law of the {std} (beta = 1.458e-6, S = 110.4 K; ref = beta T_ref^1.5 / (T_ref + S)); '
           f'conductivity: White, Viscous Fluid Flow, Table 1-3, checked against the US Std 1976 conductivity law: within '
           f'{MAX_FIT_ERROR:g} % from {Tk[klo]:g} to {Tk[khi]:g} K"', "",
           "[critical]", "T = 132.5306   # K", "p = 3.786e+06   # Pa", "acentric_factor = 0.0335",
           'source = "Lemmon, Jacobsen, Penoncello & Friend, J. Phys. Chem. Ref. Data 29 (2000) 331 (critical point of the air '
           'model, as listed by CoolProp); acentric factor as in CoolProp / REFPROP"', "",
           "[reference]", f'source = "{std}: viscosity and conductivity laws"',
           "T = [" + ", ".join(fmt(t) for t in ref_T) + "]   # K",
           "mu = [" + ", ".join(fmt(mu(t)) for t in ref_T) + "]   # Pa s",
           "k = [" + ", ".join(fmt(us_std_conductivity(t)) for t in ref_T) + "]   # W/(m K)", ""]
    (OUT / "air.toml").write_text("\n".join(out), encoding="utf-8")
    print(f"air     thermo {T[lo]:.0f}-{T[hi]:.0f} K, k (White vs US Std) within {MAX_FIT_ERROR} % {Tk[klo]:.0f}-{Tk[khi]:.0f} K, "
          f"Pr {prandtl:.3f}, mixture gamma(300 K) {cp[i300] / cv[i300]:.5f}")


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    if "--download" in sys.argv:
        download(folder)
    for gid, g in GASES.items():
        write_gas(gid, g, folder)
    write_air(folder)
