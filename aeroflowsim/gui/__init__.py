# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""GUI layer. The ONLY part of the package that may import Qt (PySide6), PyVista/VTK or streamlit.

The desktop GUI is Qt + PyVista (start it with  python -m aeroflowsim gui ). The old Streamlit
web GUI (app.py + streamlit_panel.py) stays until the desktop GUI does everything it did.
Everything a GUI needs from a case comes through plain Python objects (schema, Case, run_case,
checks, projects), so solvers never depend on the GUI.

This file imports nothing, so `import aeroflowsim.gui.panel_model` works without Qt installed.
"""
