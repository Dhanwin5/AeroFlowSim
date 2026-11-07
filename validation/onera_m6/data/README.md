# ONERA M6 data (downloaded 7 Nov 2026 with the user's approval)

Source: NASA Glenn NPARC Alliance Validation Archive, https://www.grc.nasa.gov/WWW/wind/valid/m6wing/m6wing.html
(US Government work). Original measurements: Schmitt, V. and Charpin, F., "Pressure Distributions on the ONERA-M6-Wing
at Transonic Mach Numbers", AGARD AR-138, 1979 (test 2308: M = 0.8395, alpha = 3.06 deg, Re = 11.72e6).

- `airfoil.txt`  ONERA D section, x/c and z/c (finite trailing-edge thickness)
- `foilmod.txt`  the same, trailing edge closed (zero thickness; NPARC foilmod.f90) - used for the CFD geometry
- `cp<k><l|u>.ex` measured Cp, lower / upper surface, sections k = 1..7 at y/b = 0.20, 0.44, 0.65, 0.80, 0.90, 0.95, 0.99;
  columns: x/c, Cp, and two uncertainty columns as given by NPARC
- Planform (NPARC): span b = 1.1963 m, MAC 0.64607 m, aspect ratio 3.8, taper 0.562, leading-edge sweep 30 deg,
  trailing-edge sweep 15.8 deg.
