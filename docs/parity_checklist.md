# Parity checklist: old Streamlit GUI -> desktop GUI

Every feature of the old Streamlit GUI (`app.py`) and where it is in the desktop GUI (`python -m aeroflowsim gui`).
Tick each line after checking it yourself; when all are ticked, the Streamlit GUI can be removed (a later step,
only with your OK).

| | Streamlit feature (app.py) | Desktop GUI |
|---|---|---|
| [ ] | Case choice in the sidebar | Start page: templates (new project), examples, recent projects |
| [ ] | Inputs from schema.toml (groups, units, ranges, help, show_if, files) | Inputs dock, one panel per step, help in Details |
| [ ] | Reset to defaults | File > Reset inputs to defaults (and Default per boundary row) |
| [ ] | Save / load settings files | Projects (File > Save / Open); old settings files: Import old settings on the start page |
| [ ] | Geometry preview of the shape | Geometry step (workspace for 2D templates, drawing for 1D) |
| [ ] | Derived values (areas, ratios) | Geometry summary and Properties dock |
| [ ] | Mesh tab: generate mesh, estimated cells | Mesh step: Generate mesh, cell count, quality table |
| [ ] | Mesh view with quality colouring | Mesh step: VTK view, quality fields, click a cell |
| [ ] | Download mesh .vtu | Mesh step: Save .vtu (files in the project's mesh/ folder) |
| [ ] | Run tab: run, stop, live residual | Run step: Run / Continue, Stop, Start from scratch, live residuals and monitors |
| [ ] | Progress estimate | Workflow-strip chip with progress |
| [ ] | Validity checks box | Validity checks dock |
| [ ] | Results: field plot with reference (plotly) | Results: field plot with reference (1D); Display panel (2D) |
| [ ] | Key numbers table | Key-number tiles and table |
| [ ] | Contours (shape view, x-t diagram, 2D contour) with colour map, range, exact wave paths, mesh lines | Results: colour pictures (1D); Display panel with contours, range, mesh edges (2D) |
| [ ] | Download contour PNG | Save picture (paper style) |
| [ ] | Download fields CSV, PNG | Save CSV, Save PNG; 2D: Export (CSV, VTU, Tecplot) |
| [ ] | Boundary-condition table (not in Streamlit: defaults only) | Setup step table (desktop only) |
| [ ] | Note "results from earlier inputs" | Amber banner and out-of-date status in the workflow strip |
