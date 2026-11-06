# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The AI connector: lets an AI assistant (Claude or any client that speaks MCP) drive AeroFlowSim.

    settings.py   the user's choices (off by default), stored as JSON in the app-data folder
    sandbox.py    the workspace folder: every path a tool touches must be inside it
    jobs.py       one background run at a time, with Stop and a time limit
    server.py     the MCP server over stdio (imports the optional `mcp` package; only `aeroflowsim mcp` loads it)

The tools themselves are the functions of aeroflowsim/api.py. Nothing in this package opens a network connection;
importing it imports nothing heavy.
"""
