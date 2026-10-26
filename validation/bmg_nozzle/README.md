# Back, Massier and Gier conical nozzle (experiment)

**Source:** L. H. Back, P. F. Massier and H. L. Gier, "Comparisons of Experimental with Predicted Wall
Static-Pressure Distributions in Conical Supersonic Nozzles", JPL Technical Report No. 32-654, Jet Propulsion
Laboratory, California Institute of Technology, 15 October 1964 (NASA contract NAS 7-100). Available from the NASA
Technical Reports Server, document 19650001801. The journal version is Back, Massier and Gier (1965), AIAA Journal
3(9), 1606-1614. The NPARC Alliance validation archive has no entry for this nozzle (checked October 2026), so the
data come from the original report.

**Geometry** (`bmg_45_15_profile.csv`, millimetres): built from the dimensions printed in Fig. 4 of the report:
inlet radius 2.500 in up to z = 0.31 in, inlet rounding radius 0.800 in (tangent to the cone at z = 0.876 in),
45 deg convergence to z = 2.200 in, circular-arc throat of radius r_c = 0.500 in with the throat at z = 2.554 in,
r_th = 0.800 in (r_c / r_th = 0.625), tangency at z = 2.683 in, 15 deg divergence to z = 7.285 in. Recomputed from
these values, the tangency points agree with the printed ones to 0.005 in; the exit area ratio is 6.57 (printed: 6.63).

**Data** (`bmg_wall_pressure.csv`): wall static-to-stagnation pressure ratios of Fig. 4 (hot air, T_t = 1500 R,
cooled walls), digitized from the scanned figure (300 dpi): the axes were calibrated on the plotted grid lines
(z = 0 at pixel column 261, 272 px per inch; p/p_t = 0 at row 2355.5 and 1.0 at row 1270.5), and each value is the
centroid of the dark pixels of the overlapping symbols of the unseparated runs (tests 347, 348 and 351, 150-250 psia)
in a 33 x 33 px window after removing the grid lines. Digitizing uncertainty: about +-0.005 in p/p_t. The low-pressure
runs (45-100 psia) separate downstream of z = 3.5 in and are not used.

**Comparison:** pointwise band +-0.03 in p/p0 (+-0.05 at z = 2.46 in), see `validate.py`.
