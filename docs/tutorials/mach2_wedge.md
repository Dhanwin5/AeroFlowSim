# Tutorial: a Mach 2 wedge

The classic first test of a supersonic solver: a 10° wedge in a Mach 2 stream. Inviscid theory gives an
attached, straight oblique shock from the tip at **β = 39.31°**, with **p2/p1 = 1.707** and **M2 = 1.641**
behind it (θ-β-M relation; Anderson, *Modern Compressible Flow*, sec. 4.4). You will set it up, run it and
check all three numbers. About 10 minutes, of which the run takes about 20 seconds.

1. **New project** from the template **Body in free stream (2D Euler)** (`external_2d`).
2. **Geometry step.** In the Inputs panel choose **Shape: Wedge**, half-angle `10`°, length `1` m.
   - The wedge is symmetric and the flow comes at zero angle, so half of it is enough: tick
     **Half domain** (the line y = 0 becomes a `symmetry` boundary).
   - **Domain shape: Rectangle**, upstream `0.5`, downstream `0.5`, height `1.5` (in wedge lengths L).
     Supersonic flow cannot send signals upstream, so the domain may start close to the tip; it must be high
     enough for the shock to leave through the outlet (at x = 1.5 L the shock is 1.2 L high).
   - *Suggestions…* proposes a rectangle for supersonic flow too (Mach number from the Setup step).
3. **Mesh step.** Wall cell size `0.02` L, far-field size `0.05` L, triangles; **Generate mesh**
   (about 3,500 cells). Patches: `wall`, `farfield`, `symmetry`.
4. **Setup step.**
   - **Free stream:** air, Mach `2`, 101.325 kPa, 288.15 K, angle of attack 0.
   - **Boundary conditions:** the table already has the right ones: `farfield` = Far field (the free
     stream; waves leave without reflection), `wall` = Slip wall, `symmetry` = Symmetry. Click a row's type to
     see the alternatives (a *Supersonic inlet* upstream would also do).
   - **Numerics:** press **Run step > Suggested numerics…**: for a supersonic stream it proposes 200
     first-order iterations (the shock forms smoothly before second order is switched on). Apply.
5. **Run step → Run.** The live plot shows the residual of each equation and the drag coefficient. The run
   stops by itself when the residual has dropped six orders **and** Cd has stopped changing (about 1,600
   iterations, 20 s).
6. **Results step.**
   - **Field: Mach number** shows the shock as a straight line from the tip, uniform flow behind it, and the
     expansion fan at the base corner. Tick *Mesh edges* to see the cells, click a cell to read its values
     in Properties.
   - **Plot: Pressure coefficient Cp along the wall.** On the wedge surface
     Cp = (p2/p1 − 1)/(γ/2 M²) = 0.7066/2.8 = **0.252**: the dots sit on that line (the drop at x = 1 is the
     base).
   - **Key results:** Cl = 0 and Cm = 0 (symmetry), Cd ≈ 0.197. Cd includes the base drag (the flat base sees
     the low pressure of the expansion), which is not part of the oblique-shock theory.
7. **Check the shock angle yourself.** *Field: Pressure*, zoom in and click two cells just behind the shock,
   one near the tip and one near the top: the line through them makes about 39° with the x axis. The
   validation case `validation/euler2d_wedge` does this automatically; its result (39.35°, p2/p1 = 1.7072,
   M2 = 1.632 on this mesh; 39.24°, 1.7067, 1.633 on a mesh twice as fine) is in `validation/report.md`.

**Things to try**

- Mach `1.5`: β grows to about 56.7°. Below Mach 1.42 a 10° wedge cannot hold an attached shock: it detaches
  and stands in front of the tip (then use a longer upstream region).
- Angle of attack `5`° with a full domain (untick Half domain): lift appears, Cm becomes non-zero.
- **Save .vtu…** writes every field for ParaView.
