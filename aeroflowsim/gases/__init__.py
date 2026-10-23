# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Gas library: gas models (model.py), gas data files (data.py, one <id>.toml per built-in gas in this
folder), where gases come from (library.py) and the Peng-Robinson compressibility estimate
(real_gas.py). A case gets its gas with  gas = gas_model(params["gas"])  and never hard-codes gamma
or R."""

from aeroflowsim.gases.data import GasData, VapourPressure, custom_gas_toml, parse_gas, read_gas_file
from aeroflowsim.gases.library import (PROJECT_GAS_DIR, builtin_gas, builtin_ids, gas_data, gas_model, is_builtin,
                                       save_user_gas, user_gas_dir, user_gases)
from aeroflowsim.gases.model import R_UNIVERSAL, CaloricallyPerfectGas, GasModel, TransportLaw
from aeroflowsim.gases.real_gas import peng_robinson_z

__all__ = ["GasData", "VapourPressure", "custom_gas_toml", "parse_gas", "read_gas_file", "PROJECT_GAS_DIR",
           "builtin_gas", "builtin_ids", "gas_data", "gas_model", "is_builtin", "save_user_gas", "user_gas_dir",
           "user_gases", "R_UNIVERSAL", "CaloricallyPerfectGas", "GasModel", "TransportLaw", "peng_robinson_z"]
