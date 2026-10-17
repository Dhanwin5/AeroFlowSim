# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Quasi-1D nozzle validation: two runs of the default nozzle, in the units of reference.toml.

1. p_back = 1 kPa (default): fully supersonic divergent part -> exit state, mass flow, thrust.
2. p_back = 2.5 bar: a normal shock stands in the divergent part -> its position. The residual
   stalls near 1e-3 once the shock has settled (the limiter keeps switching at the shock, see the
   case README), so 30 000 iterations are enough, as in cases/quasi1d_nozzle/test_case.py.
"""

import aeroflowsim


def measure():
    supersonic = aeroflowsim.run_case("cases/quasi1d_nozzle").result.key_numbers
    shock = aeroflowsim.run_case("cases/quasi1d_nozzle", {"p_back": 2.5e5, "max_iter": 30000}).result.key_numbers
    return {
        "M_exit": supersonic["M_exit"][0],                                   # [-]
        "p_exit": supersonic["p_exit"][0] / 1e3,                             # [Pa] -> [kPa]
        "mdot": supersonic["mdot"][0] * 1e6,                                 # [kg/s] -> [mg/s]
        "F_vacuum": supersonic["F_vacuum"][0] * 1e3,                         # [N] -> [mN]
        "x_shock": (shock["x_shock"][0] - shock["x_throat"][0]) * 1e3,      # [m] -> [mm]
    }
