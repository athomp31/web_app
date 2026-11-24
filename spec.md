# Beam Designer Specification

## 1. Purpose

Beam Designer is a desktop engineering tool for students and other users who
want to analyze a single steel W-shape beam. Users choose a section, support
condition, and vertical loads; the app calculates reactions, shear, bending
moment, deflection, and basic bending and deflection checks.

The app is for educational and preliminary analysis, not a substitute for
professional engineering judgment or design review.

## 2. Inputs

All numeric fields accept finite numbers. The interface provides editable
numeric fields for span and load values, dropdowns for section, grade, and
support type, buttons to add or remove load rows, a horizontal slider paired
with the selected point load's location field, and a checkbox for self-weight.

| Input | Unit | Allowed values / range | Initial example |
|---|---|---|---|
| W-shape section | Catalog section name | A section available in the documented property catalog | W12x26 |
| Steel grade | Catalog grade | A grade available for the selected section | A992 |
| Support condition | — | Simply supported or cantilever | Simply supported |
| Span | ft | Greater than 0 | 20 |
| Point-load magnitude | kip | 0 or greater; direction is selected separately | None |
| Point-load direction | — | Up or down | Down for the example |
| Point-load location from left end | ft | 0 through the span, inclusive | None |
| Uniform-load intensity | kip/ft | 0 or greater; direction is selected separately | 1 |
| Uniform-load direction | — | Up or down | Down |
| Uniform-load start and end | ft | Both within 0 through the span; start must be less than end | 0 and 20 |
| Include section self-weight | — | On or off | Off |

The initial example is a 20 ft simply supported W12x26 (A992), with a 1 kip/ft
downward uniform load over the full span and self-weight disabled. Point and
uniform loads may be added or removed; multiple loads can overlap and are
combined. There is no separate arbitrary maximum load count or magnitude.
Section properties and material values must come from the documented catalog;
the app identifies the catalog used.

Invalid, missing, or non-finite numeric entries, a non-positive span, load
positions outside the span, and a uniform load whose start is not before its
end are rejected with a clear message. The app does not silently substitute
values for invalid entries.

## 3. Calculations

### Units and sign convention

Entered distances in ft are converted to inches (in), and uniform-load
intensities in kip/ft are converted to kip/in. Internal units are kip, in,
ksi (kip/in^2), and kip-in. Let:

- `x` be distance from the left end (in), and `L` be the span (in).
- `P` be a signed point load (kip), positive upward.
- `q(x)` be signed distributed load intensity (kip/in), positive upward.
- `R_A` and `R_B` be support vertical reactions (kip), positive upward.
- `M_A` be a support reaction moment (kip-in), with positive sign matching
  positive sagging beam moment.
- `V(x)` be shear (kip), `M(x)` be bending moment (kip-in), and `v(x)` be
  vertical deflection (in), positive upward.
- Positive bending moment is sagging. Use these signs consistently in
  calculations, diagrams, and displayed values.

### Reactions, shear, and moment

Find support reactions from static equilibrium:

- `sum(F_y) = 0`, including reactions, point loads, distributed-load
  resultants, and self-weight if enabled.
- `sum(M) = 0` about a support. A uniform load over `[a, b]` has resultant
  `q * (b - a)` at its centroid `(a + b) / 2`.

Build `V(x)` from the signed vertical forces to the left of `x`, and `M(x)`
from their moments about the section at `x`, including any support reaction
moment. Distributed loads are integrated over their loaded lengths. Overlapping
loads add algebraically. The bending check uses
`M_max = max_x(abs(M(x)))`.

### Deflection and checks

Assume a prismatic, linearly elastic beam and small deflections. Calculate
deflection from `E * I * v''(x) = M(x)`, applying the selected support's
boundary conditions: zero displacement at both ends for a simply supported
beam; zero displacement and rotation at the fixed end for a cantilever. Report
`delta_max = max_x(abs(v(x)))` in inches.

Use the selected section and grade's catalog values for:

- `E`: modulus of elasticity (ksi)
- `I`: area moment of inertia about the bending axis (in^4)
- `S`: section modulus about the bending axis (in^3)
- `F_b`: allowable bending stress (ksi)
- section weight per unit length (converted to kip/in if self-weight is on)

Calculate bending stress as `f_b = M_max / S` (ksi) and compare it with `F_b`.
The deflection limit is `L / 360` (in). Both checks pass when actual value is
less than or equal to its allowable value. Deflection includes all entered
loads and self-weight when enabled; no separate load combinations are
supported. Shear is calculated and plotted but has no strength pass/fail check.

## 4. Outputs

- Support reactions, maximum absolute shear, maximum absolute moment, and
  maximum absolute deflection, each with units and the location of its maximum.
- A beam drawing with support symbols, point-load arrows, uniform-load arrow
  rows, and reaction arrows in their respective directions.
- Three diagrams sharing the beam's horizontal scale: shear (kip), moment
  (kip-ft), and deflected shape (in). Convert moment from kip-in to kip-ft for
  display. Label maxima with value, sign, and location.
- A synchronized readout when the user points to, focuses, or selects a
  diagram position: `V` (kip), `M` (kip-ft), and `v` (in) at that `x`.
- Bending and deflection check cards showing actual and allowable values,
  units, PASS/FAIL, and an actual-to-allowable ratio bar. Use green below 70%,
  amber from 70% through 100%, and red above 100%; exactly 100% passes.
- Refresh the drawing, diagrams, values, and checks when inputs change.
- Export the current results and load inputs as either CSV or an Excel
  (`.xlsx`) workbook.

## 5. Features

- Provide an export-format dropdown with CSV and Excel (`.xlsx`) choices and
  an Export button. Export the current beam and load inputs, support reactions,
  result values, bending and deflection checks, and sampled shear, moment, and
  deflection diagram data. Let the user choose the output file location and
  report export errors clearly.
- Let the user select a point load and move it along the beam with a slider
  spanning 0 through the current beam length. Keep the slider and numeric
  position field synchronized. As the slider moves, redraw the beam and
  diagrams and recalculate reactions, shear, moment, deflection, and checks
  continuously; in particular, show the moment diagram changing with the
  point load's position. The slider must respect the same position validation
  as the numeric field.

## 6. Look and feel

Use a light-mode Tkinter desktop window. Arrange the window with the beam
configuration controls (section, grade, support, span, self-weight, and
editable load rows and selected point-load slider) in a clearly labeled input
pane, and the beam drawing, diagrams, numerical results, export controls, and
check cards in a results pane. Keep primary actions such as adding/removing
loads and resetting the example easy to find. Show validation feedback next to
the relevant inputs or in a clear message.

Use Papyrus with a fantasy-serif fallback where available, and a palette of
green, orange, purple, and red; amber is also used for the specified check-card
range. Draw the beam's deflected shape with visual exaggeration if needed, but
keep the deflection diagram and numeric values accurate. Open with the example
beam and load described in Inputs.

## 7. Validation

Reject invalid input as described in Inputs. The following calculation checks
are required regression cases; use `E = 29,000 ksi` and `I_x = 204 in^4` for
the cases that specify them. Tolerances should account for displayed rounding,
while internal calculations should be compared at full precision.

1. **Simply supported full-span uniform load:** A 20 ft W12x26 (A992) beam,
   with a 1 kip/ft downward load over the full span and self-weight off, has
   reactions of 10 kip upward at each support, maximum absolute shear of
   10 kip, maximum absolute moment of 50.0 kip-ft, and maximum absolute
   deflection of approximately 0.609 in.
2. **Simply supported center point load:** A 20 ft simply supported beam with
   a 10 kip downward point load at midspan has reactions of 5 kip upward at
   each support, maximum absolute shear of 5 kip, maximum absolute moment of
   50.0 kip-ft, and maximum absolute deflection of approximately 0.487 in.
3. **Cantilever end point load:** A 10 ft cantilever with a 1 kip downward
   point load at its free end has a 1 kip upward vertical reaction and a
   10 kip-ft fixed-end reaction moment. Maximum absolute moment is 10 kip-ft,
   and maximum absolute deflection at the free end is approximately 0.0974 in.

## 8. Validation results

The expected values below were calculated by the user with another resource;
the actual values are from the agent's direct check of the calculation engine.
All cases use a simply supported beam with one downward point load at midspan,
no other loads, no self-weight, `E = 29,000 ksi`, and `I = 1,000 in^4`.

The calculation engine was given these exact property assumptions for the
check. The Tkinter interface does not currently allow `I = 1,000 in^4`: it
only offers the embedded sample sections with `I_x` values of 204, 238, 285,
or 350 in^4. These results therefore validate the calculation engine for the
stated cases, not a setup entered through the current interface.

| Case | Measure | Expected (user-solved with another resource) | Actual (agent's calculation-engine check) |
|---|---|---:|---:|
| 1: 10 kip, 20 ft | Reactions | 5 kip each | 5 kip each |
| 1: 10 kip, 20 ft | Maximum absolute shear | 5 kip | 5 kip |
| 1: 10 kip, 20 ft | Maximum absolute moment | 50 kip-ft | 50 kip-ft |
| 1: 10 kip, 20 ft | Maximum absolute deflection | 0.09931 in | 0.09930991 in |
| 2: 8 kip, 16 ft | Reactions | 4 kip each | 4 kip each |
| 2: 8 kip, 16 ft | Maximum absolute shear | 4 kip | 4 kip |
| 2: 8 kip, 16 ft | Maximum absolute moment | 32 kip-ft | 32 kip-ft |
| 2: 8 kip, 16 ft | Maximum absolute deflection | 0.04068 in | 0.04067734 in |
| 3: 20 kip, 20 ft | Reactions | 10 kip each | 10 kip each |
| 3: 20 kip, 20 ft | Maximum absolute shear | 10 kip | 10 kip |
| 3: 20 kip, 20 ft | Maximum absolute moment | 100 kip-ft | 100 kip-ft |
| 3: 20 kip, 20 ft | Maximum absolute deflection | 0.19862 in | 0.19861983 in |

Doubling the Case 1 point load to obtain Case 3 doubled both reactions,
maximum absolute shear, maximum absolute moment, and maximum absolute
deflection.

The expected values in the table are the user's calculations, based on:

- **Case 1:** `L = 20 ft = 240 in`; `R_L = R_R = P / 2 = 10 / 2 = 5 kip`;
  `M_max = P L / 4 = (10 kip)(20 ft) / 4 = 50 kip-ft`;
  `delta_max = P L^3 / (48 E I) = 10(240)^3 / (48(29,000)(1,000))
  = 0.09931 in`.
- **Case 2:** `L = 16 ft = 192 in`; `R_L = R_R = P / 2 = 8 / 2 = 4 kip`;
  `M_max = P L / 4 = (8 kip)(16 ft) / 4 = 32 kip-ft`;
  `delta_max = P L^3 / (48 E I) = 8(192)^3 / (48(29,000)(1,000))
  = 0.04068 in`.
- **Case 3:** Same span, `E`, and `I` as Case 1, with `P = 20 kip` (twice the
  Case 1 load), so the expected reactions, shear, moment, and deflection are
  twice the Case 1 values.

## 9. Out of scope

- Lumber or non-W-shape members, automatic lightest-section search,
  continuous beams, buckling checks, and shear-strength checks.
- Multiple spans, non-vertical loads, dynamic analysis, and load combinations.
- Use as a replacement for professional engineering review.

## 10. Platform

Implement the desktop application in Python with a Tkinter interface. Launch
it from the `CCE 270` directory with:

```text
python my_desktop_app.py
```
