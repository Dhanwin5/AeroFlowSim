# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The gas model: the ONE interface through which every solver gets gas properties.

A solver never writes gamma = 1.4 or R = 287 itself. It asks a GasModel:

    gas.R                       specific gas constant [J/(kg K)]
    gas.cp(T), gas.cv(T)        specific heats [J/(kg K)]
    gas.gamma(T)                cp / cv [-]
    gas.sound_speed(T)          c = sqrt(gamma R T) [m/s] (ideal gas)
    gas.internal_energy(T)      e(T) [J/kg], zero at T = 0 for a calorically perfect gas
    gas.temperature(e)          T from e (the inverse; a solver gets e from its conserved energy)
    gas.mu(T), gas.k(T)         dynamic viscosity [Pa s] and thermal conductivity [W/(m K)]
    gas.prandtl(T)              Pr = mu cp / k [-]
    gas.thermo_range            (T_min, T_max) [K] where cp, gamma are valid
    gas.transport_range         (T_min, T_max) [K] where mu, k are valid
    gas.data                    the GasData behind it (critical point, vapour pressure, sources...)

Every method takes a number or a numpy array of temperatures (one per cell), so a 2D solver calls
gas.mu(T) once for the whole mesh. Because solvers only use this interface, a thermally perfect gas
(NASA polynomials, cp(T)), a mixture or a real gas (Peng-Robinson, Phase 5) is a new subclass and
needs no change in any solver.

Implemented now: CaloricallyPerfectGas - constant cp and gamma, so e = cv T and c = sqrt(gamma R T).
Transport laws (see TransportLaw):
    Sutherland   x(T) = x_ref (T / T_ref)^(3/2) (T_ref + S) / (T + S)
    power law    x(T) = x_ref (T / T_ref)^n
    Prandtl      k(T) = mu(T) cp / Pr        (conductivity from viscosity and a constant Prandtl number)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

R_UNIVERSAL = 8.314462618    # molar gas constant [J/(mol K)] (CODATA 2018, exact since the 2019 SI)


@dataclass(frozen=True)
class TransportLaw:
    """A temperature law for viscosity [Pa s] or conductivity [W/(m K)]."""

    law: str            # "sutherland" or "power"
    ref: float          # value at T_ref (mu_ref [Pa s] or k_ref [W/(m K)])
    T_ref: float        # reference temperature [K]
    S: float = 0.0      # Sutherland temperature [K] (law "sutherland")
    n: float = 0.0      # exponent [-] (law "power")

    def __post_init__(self):
        if self.law not in ("sutherland", "power"):
            raise ValueError(f"unknown transport law '{self.law}' (use 'sutherland' or 'power').")
        if not (self.ref > 0.0 and self.T_ref > 0.0):
            raise ValueError("the reference value and reference temperature must be positive.")
        if self.law == "sutherland" and self.S < 0.0:
            raise ValueError("the Sutherland temperature S must not be negative.")

    def __call__(self, T):
        T = np.asarray(T, dtype=float)
        if self.law == "sutherland":
            return self.ref * (T / self.T_ref) ** 1.5 * (self.T_ref + self.S) / (T + self.S)
        return self.ref * (T / self.T_ref) ** self.n

    def describe(self, unit) -> str:
        """Short text for the GUI, e.g. 'Sutherland: 1.716e-05 Pa s at 273.15 K, S = 110.4 K'."""
        if self.law == "sutherland":
            return f"Sutherland: {self.ref:.5g} {unit} at {self.T_ref:g} K, S = {self.S:g} K"
        return f"power law: {self.ref:.5g} {unit} at {self.T_ref:g} K, exponent {self.n:g}"


class GasModel(ABC):
    """What every solver may ask of a gas (see the module docstring)."""

    def __init__(self, data):
        self.data = data                # GasData: constants, critical point, curves, sources

    @property
    def id(self) -> str:
        return self.data.id

    @property
    def name(self) -> str:
        return self.data.name

    @property
    def R(self) -> float:
        """Specific gas constant [J/(kg K)]."""
        return self.data.R

    @property
    def molar_mass(self) -> float:
        """[kg/mol]"""
        return self.data.molar_mass

    @abstractmethod
    def cp(self, T): ...

    def cv(self, T):
        return self.cp(T) - self.R

    def gamma(self, T):
        return self.cp(T) / self.cv(T)

    def sound_speed(self, T):
        """Speed of sound of an ideal gas, c = sqrt(gamma R T) [m/s]."""
        T = np.asarray(T, dtype=float)
        return np.sqrt(self.gamma(T) * self.R * T)

    @abstractmethod
    def internal_energy(self, T): ...

    @abstractmethod
    def temperature(self, e): ...

    @abstractmethod
    def mu(self, T): ...

    @abstractmethod
    def k(self, T): ...

    def prandtl(self, T):
        return self.mu(T) * self.cp(T) / self.k(T)

    @property
    def thermo_range(self) -> tuple:
        return self.data.thermo_range

    @property
    def transport_range(self) -> tuple:
        return self.data.transport_range

    def __repr__(self):
        return f"{type(self).__name__}({self.id!r})"


class CaloricallyPerfectGas(GasModel):
    """Ideal gas with constant cp and gamma: p = rho R T, e = cv T, c = sqrt(gamma R T)."""

    def __init__(self, data):
        super().__init__(data)
        g = data.gamma
        self._gamma = g                       # [-]
        self._cp = g * data.R / (g - 1.0)     # [J/(kg K)]
        self._cv = data.R / (g - 1.0)         # [J/(kg K)]

    def _const(self, T, value):
        T = np.asarray(T, dtype=float)
        return value if T.ndim == 0 else np.full(T.shape, value)

    def cp(self, T):
        return self._const(T, self._cp)

    def cv(self, T):
        return self._const(T, self._cv)

    def gamma(self, T=300.0):
        return self._const(T, self._gamma)

    def internal_energy(self, T):
        return self._cv * np.asarray(T, dtype=float)

    def temperature(self, e):
        return np.asarray(e, dtype=float) / self._cv

    def mu(self, T):
        return self.data.viscosity(T)

    def k(self, T):
        if self.data.conductivity is not None:
            return self.data.conductivity(T)
        return self.mu(T) * self._cp / self.data.prandtl      # from a constant Prandtl number

    # Constant-property shortcuts for 1D solvers that work with one gamma (plain floats):
    @property
    def gamma_value(self) -> float:
        return self._gamma

    @property
    def cp_value(self) -> float:
        return self._cp
