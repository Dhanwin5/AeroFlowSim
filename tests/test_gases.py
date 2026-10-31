# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Gas library (aeroflowsim/gases/): every built-in gas against its source data, the GasModel
interface, Peng-Robinson Z, the saturation curves, custom gases, gases in projects, and the three
gas validity checks."""

import math
import shutil
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from aeroflowsim import checks
from aeroflowsim.discovery import load_case
from aeroflowsim.gases import (R_UNIVERSAL, builtin_gas, builtin_ids, custom_gas_toml, gas_data, gas_model,
                               parse_gas, peng_robinson_z, save_user_gas, user_gas_dir)
from aeroflowsim.gases.model import TransportLaw
from aeroflowsim.parameters import Parameter, clean_value
from aeroflowsim.project import Project
from aeroflowsim.results import Field, Result

ALL = ["N2", "air", "O2", "Ar", "He", "Kr", "Xe", "CO2", "H2", "H2O", "R236fa"]


def test_the_library_has_every_gas_of_the_plan_in_dropdown_order():
    assert builtin_ids() == ALL


@pytest.mark.parametrize("gid", ALL)
def test_every_gas_names_its_sources_and_has_consistent_constants(gid):
    g = builtin_gas(gid)
    assert g.builtin and g.name and g.path.name == f"{gid}.toml"
    for key in ("molar_mass", "gamma", "T_range", "transport", "critical"):
        assert g.sources.get(key), f"{gid}: no source for {key}"
    assert g.R == pytest.approx(R_UNIVERSAL / g.molar_mass, rel=1e-4)       # tabulated R within 0.01 %
    assert 1.0 < g.gamma <= 5.0 / 3.0 + 1e-12
    assert g.has_critical_point and g.thermo_range[0] < 300.0 < g.thermo_range[1]
    assert g.transport_range[0] < g.transport_range[1]


def test_n2_keeps_the_validated_quasi1d_values_exactly():
    g = gas_model("N2")
    assert (g.gamma_value, g.R) == (1.4, 296.8)
    assert "296.803" in builtin_gas("N2").note                          # R_u / M is said openly


@pytest.mark.parametrize("gid", ["Ar", "He", "Kr", "Xe"])
def test_monatomic_gases_have_gamma_five_thirds(gid):
    assert gas_model(gid).gamma_value == 5.0 / 3.0


@pytest.mark.parametrize("gid", [g for g in ALL if g != "air"])
def test_constant_cp_and_gamma_match_the_nist_data(gid):
    g, ref = gas_model(gid), builtin_gas(gid).reference
    T, cp, cv = (np.array(ref[k]) for k in ("T", "cp", "cv"))
    i = int(np.argmin(abs(T - 300.0)))
    assert g.gamma_value == pytest.approx(cp[i] / cv[i], rel=5e-4)      # 4 decimals (N2: 1.4 vs 1.3995)
    inside = (T >= g.thermo_range[0]) & (T <= g.thermo_range[1])
    assert np.all(np.abs(g.cp(T[inside]) / cp[inside] - 1.0) <= 0.0201)  # the range is where cp is within 2 %


@pytest.mark.parametrize("gid", ALL)
def test_viscosity_and_conductivity_laws_match_the_source_data(gid):
    g, data = gas_model(gid), builtin_gas(gid)
    ref = data.reference
    T = np.array(ref["T"])
    inside = (T >= data.transport_range[0]) & (T <= data.transport_range[1])
    assert inside.any()
    tolerance = data.transport_error_percent / 100.0 + 1e-4
    assert np.all(np.abs(g.mu(T[inside]) / np.array(ref["mu"])[inside] - 1.0) <= tolerance)
    assert np.all(np.abs(g.k(T[inside]) / np.array(ref["k"])[inside] - 1.0) <= tolerance)


@pytest.mark.parametrize("gid", [g for g in ALL if g != "air"])
def test_prandtl_number_is_the_nist_value_at_300_k(gid):
    ref = builtin_gas(gid).reference
    i = int(np.argmin(abs(np.array(ref["T"]) - 300.0)))
    assert builtin_gas(gid).prandtl == pytest.approx(ref["mu"][i] * ref["cp"][i] / ref["k"][i], rel=2e-3)


def test_air_follows_the_us_standard_atmosphere():
    g = gas_model("air")
    assert (g.gamma_value, g.R) == (1.4, 287.053)
    assert g.mu(288.15) == pytest.approx(1.7894e-5, rel=1e-4)            # US Std 1976 sea-level viscosity
    assert g.sound_speed(288.15) == pytest.approx(340.294, rel=1e-5)    # US Std 1976 sea-level speed of sound


# ---- the GasModel interface -------------------------------------------------------------------

def test_gas_model_interface_relations_on_arrays():
    g = gas_model("N2")
    T = np.array([100.0, 300.0, 500.0])
    assert g.cp(T).shape == T.shape and np.allclose(g.cp(T) - g.cv(T), g.R)
    assert np.allclose(g.gamma(T), g.cp(T) / g.cv(T))
    assert np.allclose(g.sound_speed(T), np.sqrt(1.4 * 296.8 * T))
    assert g.sound_speed(300.0) == pytest.approx(353.009, rel=2e-4)       # NIST, 0.1 kPa, 300 K
    assert np.allclose(g.temperature(g.internal_energy(T)), T)
    assert np.allclose(g.prandtl(T), g.mu(T) * g.cp(T) / g.k(T))
    assert g.thermo_range == builtin_gas("N2").thermo_range and repr(g) == "CaloricallyPerfectGas('N2')"


def test_transport_laws_by_hand():
    s = TransportLaw("sutherland", ref=1.716e-5, T_ref=273.15, S=110.4)
    assert s(273.15) == pytest.approx(1.716e-5)
    assert s(500.0) == pytest.approx(1.716e-5 * (500 / 273.15) ** 1.5 * (273.15 + 110.4) / (500 + 110.4))
    p = TransportLaw("power", ref=2.0e-5, T_ref=300.0, n=0.7)
    assert p(600.0) == pytest.approx(2.0e-5 * 2.0**0.7)
    with pytest.raises(ValueError):
        TransportLaw("magic", ref=1.0, T_ref=1.0)


def test_conductivity_from_the_prandtl_number_when_no_law_is_given():
    text = custom_gas_toml("Mix", "mix", molar_mass=0.03, gamma=1.3, prandtl=0.7,
                           viscosity={"law": "power", "ref": 2e-5, "T_ref": 300.0, "n": 0.7})
    g = gas_model(parse_gas(__import__("tomllib").loads(text)))
    assert g.k(400.0) == pytest.approx(g.mu(400.0) * g.cp(400.0) / 0.7)
    assert g.thermo_range == (0.0, math.inf)


# ---- real gas and saturation ------------------------------------------------------------------

def test_peng_robinson_against_nist_densities():
    n2 = builtin_gas("N2")
    crit = (n2.T_critical, n2.p_critical, n2.acentric_factor)
    z_nist = 3.0e7 / (302.439 * (R_UNIVERSAL / 0.0280134) * 293.15)    # NIST: 302.439 kg/m3 at 300 bar, 293.15 K
    assert z_nist == pytest.approx(1.1402, abs=1e-3)
    # At 300 bar the gas is as dense as at its critical point: Peng-Robinson gives Z = 1.092, i.e. it
    # underestimates |Z - 1| (9 % instead of 14 %) - still far above the 2 % warning limit (see theory manual).
    assert peng_robinson_z(3.0e7, 293.15, *crit) == pytest.approx(z_nist, rel=0.05)
    assert peng_robinson_z(5.0e6, 293.15, *crit) == pytest.approx(5.0e6 / (57.8146 * 296.803 * 293.15), rel=0.015)
    assert peng_robinson_z(1.0e3, 293.15, *crit) == pytest.approx(1.0, abs=1e-4)   # dilute gas: ideal
    r = builtin_gas("R236fa")
    z_sat = 2.29355e5 / (15.5934 * (R_UNIVERSAL / 0.1520384) * 293.15)  # NIST saturated vapour at 20 C
    assert peng_robinson_z(2.29355e5, 293.15, r.T_critical, r.p_critical, r.acentric_factor) == \
        pytest.approx(z_sat, rel=0.015)
    assert peng_robinson_z(np.array([1e5, 2e5]), np.array([300.0, 300.0]), *crit).shape == (2,)


def test_saturation_curve_matches_nist_boiling_points_and_inverts():
    for gid, T_boil in (("N2", 77.355), ("O2", 90.1878), ("Ar", 87.302), ("Kr", 119.73), ("Xe", 165.05),
                        ("H2O", 373.1243), ("R236fa", 271.66)):
        curve = builtin_gas(gid).vapour_pressure
        assert float(curve.p_sat(T_boil)) == pytest.approx(101325.0, rel=3e-3), gid   # NIST normal boiling point
        assert float(curve.T_sat(101325.0)) == pytest.approx(T_boil, abs=0.05), gid
    curve = builtin_gas("N2").vapour_pressure
    assert float(curve.p_sat(curve.T_triple)) == pytest.approx(12519.8)
    assert float(curve.p_sat(130.0)) == math.inf                      # above the critical point: no condensation
    T = np.array([50.0, 56.0, 60.0])                                   # below the triple point: extrapolated
    assert curve.extrapolated(T) and np.all(np.diff(curve.p_sat(T)) > 0)
    assert np.allclose(curve.T_sat(curve.p_sat(T)), T)


# ---- inputs, custom gases and projects ----------------------------------------------------------

def test_gas_input_values():
    p = Parameter("gas", "Gas", "", "N2", type="gas")
    assert clean_value(p, "Kr") == "Kr" and clean_value(p, "gases/My gas.toml") == "gases/My gas.toml"
    with pytest.raises(ValueError, match="neither a built-in gas"):
        clean_value(p, "unobtainium")


def test_custom_gas_with_r_and_cp_round_trips(tmp_path):
    text = custom_gas_toml("Test gas", "test", R=300.0, cp=1050.0, prandtl=0.72,
                           viscosity={"law": "sutherland", "ref": 1.7e-5, "T_ref": 273.15, "S": 110.0})
    path = save_user_gas(text, "Test gas", folder=tmp_path)
    g = gas_model(path)
    assert path.name == "Test gas.toml" and g.R == 300.0 and g.cp_value == pytest.approx(1050.0)
    assert g.molar_mass == pytest.approx(R_UNIVERSAL / 300.0)
    with pytest.raises(ValueError, match="gamma must lie"):
        custom_gas_toml("Bad", "bad", R=300.0, gamma=2.5, viscosity={"law": "power", "ref": 1e-5, "T_ref": 300, "n": 0.7})
    with pytest.raises(ValueError, match="give the molar mass"):
        parse_gas({"id": "x", "name": "x", "constants": {"gamma": 1.4}})


def test_user_library_is_outside_the_code_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))                 # macOS: ~/Library/Application Support/AeroFlowSim
    folder = user_gas_dir()
    assert tmp_path in folder.parents and folder.name == "gases"
    from aeroflowsim.discovery import PROJECT_DIR
    assert PROJECT_DIR not in folder.parents


def _custom_file(tmp_path, gamma=1.3):
    text = custom_gas_toml("Lab gas", "lab", molar_mass=0.044, gamma=gamma, prandtl=0.75,
                           viscosity={"law": "power", "ref": 1.4e-5, "T_ref": 273.15, "n": 0.85})
    return save_user_gas(text, "Lab gas", folder=tmp_path / "library")


def test_a_project_copies_its_custom_gas_and_stays_reproducible(tmp_path):
    project = Project.create("quasi1d_nozzle", tmp_path / "P.afsproj")
    assert project.values["gas"] == "N2"
    value = project.import_gas(_custom_file(tmp_path))
    assert value == "gases/Lab gas.toml" and (project.folder / value).is_file()
    project.set_value("gas", value)
    project.save()
    params = project.params()
    assert load_case("quasi1d_nozzle").gas(params).gamma_value == 1.3
    before = project.fingerprint("run")
    shutil.rmtree(tmp_path / "library")                                # the user library may change or vanish
    moved = shutil.copytree(project.folder, tmp_path / "elsewhere" / "P.afsproj")   # e.g. zipped and shared
    copy = Project.open(moved)
    assert copy.fingerprint("run") == before and copy.case.gas(copy.params()).gamma_value == 1.3
    (moved / value).write_text((moved / value).read_text().replace("gamma = 1.3", "gamma = 1.31"))
    assert copy.fingerprint("run") != before                            # a changed gas makes results outdated


def test_choosing_a_built_in_gas_changes_the_fingerprint(tmp_path):
    project = Project.create("quasi1d_nozzle", tmp_path / "P.afsproj")
    before = project.fingerprint("run")
    project.set_value("gas", "Kr")
    assert project.fingerprint("run") != before and project.fingerprint("mesh") == Project.open(
        project.folder).fingerprint("mesh")                            # the gas is a Setup input, not a mesh input


@pytest.mark.parametrize("gamma, R, expected", [(1.4, 296.8, "N2"), (1.66, 2077.0, "gases/converted gas.toml")])
def test_old_projects_with_gamma_and_r_are_converted(tmp_path, gamma, R, expected):
    project = Project.create("quasi1d_nozzle", tmp_path / "Old.afsproj")
    data = yaml.safe_load((project.folder / "project.yaml").read_text())
    data["inputs"].pop("gas")
    data["inputs"].update(gamma=gamma, R=R)
    (project.folder / "project.yaml").write_text(yaml.safe_dump(data))
    old = Project.open(project.folder)
    assert old.values["gas"] == expected and old.dirty
    g = old.case.gas(old.params())
    assert (g.gamma_value, g.R) == (pytest.approx(gamma), pytest.approx(R))
    assert any("gamma" in w for w in old.warnings)


# ---- the three gas validity checks ---------------------------------------------------------------

Q1D = load_case("quasi1d_nozzle")


def states(T, p, **params):
    """A made-up quasi-1D result with these temperatures [K] and pressures [Pa]."""
    values = {"gas": "N2", "p0": 5e5, "T0": 293.15, **params}
    result = Result(residuals=[], fields={"T": Field(np.asarray(T, float), "K", "Temperature"),
                            "p": Field(np.asarray(p, float), "Pa", "Pressure")})
    return values, result


def test_ideal_gas_check():
    params, result = states([293.0, 200.0, 70.3], [5e5, 1.3e5, 3.37e3])
    check = checks.ideal_gas_validity(Q1D, params, None, result)
    assert check.level == "info" and check.value < 1.0
    params, result = states([293.0, 200.0], [3e7, 1e6], p0=3e7)       # the user's 300 bar tank
    check = checks.ideal_gas_validity(Q1D, params, None, result)
    assert check.level == "warning" and "reservoir" in check.message and check.value == pytest.approx(9.2, abs=0.5)


def test_condensation_check_reports_the_exit_margin():
    params, result = states([293.0, 150.0, 70.3], [5e5, 6e4, 3.37e3])
    check = checks.condensation_risk(Q1D, params, None, result)
    assert check.level == "info" and "exit: T = 70.3 K" in check.message and "upper limit" in check.message
    assert check.value == pytest.approx(13.6, abs=0.5)                 # frost point about 56.7 K
    params, result = states([293.0, 70.3], [5e5, 2.0e5])               # 2 bar at 70 K: liquid nitrogen
    assert checks.condensation_risk(Q1D, params, None, result).level == "warning"
    params, result = states([293.0, 280.0], [2e5, 1e5], gas="R236fa", p0=3e5)   # 3 bar at 20 C: liquid
    check = checks.condensation_risk(Q1D, params, None, result)
    assert check.level == "warning" and "LIQUID" in check.message
    params, result = states([293.0, 70.0], [5e5, 3e3], gas="air")
    assert "No saturation curve" in checks.condensation_risk(Q1D, params, None, result).message


def test_temperature_range_check():
    params, result = states([293.0, 70.3], [5e5, 3.37e3])
    assert checks.temperature_range(Q1D, params, None, result).level == "info"
    params, result = states([293.0, 103.0], [5e5, 4.6e3], gas="CO2")
    check = checks.temperature_range(Q1D, params, None, result)
    assert check.level == "warning" and check.value == pytest.approx(103.0)


def test_gas_checks_do_not_apply_without_a_gas_model():
    sod = SimpleNamespace(steady=False)
    result = Result(residuals=[], fields={"T": Field(np.ones(3), "K", "T"), "p": Field(np.ones(3), "Pa", "p")})
    for check in checks.GAS_CHECKS:
        assert check(sod, {}, None, result) is None
        assert check(Q1D, {"gas": "N2"}, None, Result(residuals=[], fields={})) is None
