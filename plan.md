# Beam Designer implementation plan

## Milestones

1. **Specification:** Record purpose, inputs and units, calculation rules,
   outputs, desktop layout, platform, feature requirements, and validation
   cases in `spec.md`.
2. **Plan:** Keep this workflow alongside the project requirements.
3. **First working version:** Port the web app's W-shape beam model and
   calculations to Python, then provide input controls and plots in Tkinter.
4. **Validated version:** Compare reactions, shear, moment, and deflection
   with the specified benchmark cases; record user-calculated expected values
   separately from calculation-engine results.
5. **CSV and Excel export:** Export the current model, checks, and sampled
   diagram results to CSV or XLSX.
6. **Live point-load slider:** Synchronize the selected point load's slider
   and position input, recalculating the analysis as the slider moves.

The export and slider requirements were specified before the first desktop
implementation, so both are already present in the first working version.
Their separate feature milestones below add focused verification rather than
misrepresenting when the features were implemented.

## Verification

- Run the calculation regression tests for the specified beam cases.
- Check invalid load ranges are rejected.
- Verify CSV and XLSX output files.
- Exercise the Tkinter slider and confirm moving a point load changes the
  displayed analysis.
