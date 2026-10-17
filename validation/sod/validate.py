# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sod shock tube validation: run the default case (the standard Sod problem) and measure the
star-region plateaus and the wave positions, in the units of reference.toml."""

import numpy as np

import aeroflowsim


def measure():
    out = aeroflowsim.run_case("cases/sod_shock_tube")     # defaults: Toro test 1, 400 cells, t = 0.2 s
    x = out.mesh.xc                                        # cell centres [m]
    f, k = out.result.fields, out.result.key_numbers
    x0 = out.params["x0"]                                  # diaphragm position [m]

    def at(key, position):
        """Field value at a position [m] (linear interpolation between cell centres)."""
        return float(np.interp(position, x, f[key].values))

    # x = 0.6 m lies between the rarefaction tail (0.486 m) and the contact (0.685 m);
    # x = 0.75 m between the contact and the shock (0.850 m): both inside flat plateaus.
    return {
        "p_star": at("p", 0.75),                           # [Pa]
        "u_star": at("u", 0.75),                           # [m/s]
        "rho_star_L": at("rho", 0.6),                      # [kg/m³]
        "rho_star_R": at("rho", 0.75),                     # [kg/m³]
        "shock_travel": k["x_shock"][0] - x0,              # [m]
        "contact_travel": k["x_contact"][0] - x0,          # [m]
    }
