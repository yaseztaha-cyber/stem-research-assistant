# Lab Manual: Thermoelectric Generator Characterization

## Objective
Measure the performance of a commercial Bi2Te3 thermoelectric module as a function of temperature difference and load resistance, verifying V = S ΔT and P = V I.

## Materials
- Bi2Te3 TEG module (40x40 mm)
- Hot plate with temperature controller
- Aluminum heat sink with fan (cold side)
- Thermocouples (K-type) x2
- Electronic load / decade resistance box (1-10 Ω)
- Multimeters (voltage, current)
- Thermal paste
- Safety gloves, goggles

## Safety Information
⚠️ **Hot surfaces up to 150°C — use thermal gloves, do not touch hot plate directly.**
⚠️ **Electrical: Low voltage (<5V) but current up to 2A — avoid short circuits.**
- Ensure heat sink fan is running to avoid overheating.
- Allow 10 minutes cool-down before disassembly.

## Procedure
1. Apply thermal paste, mount TEG between hot plate and heat sink.
2. Set hot side to 80°C, cold side ambient, wait for steady state (ΔT ≈ 50K).
3. Connect load resistor R = 4 Ω, measure V and I.
4. Repeat for R = 2, 6, 8, 10 Ω.
5. Increase ΔT to 100K and 120K, repeat steps 3-4.
6. Record V, I, calculate P = V * I for each.

## Variables
- Independent: ΔT, R_load
- Dependent: V, I, P
- Controlled: Thermal contact pressure, ambient temperature

## Measurements
Record in table: ΔT (K), R (Ω), V (V), I (A), P (W)

## Expected Observations
- V increases linearly with ΔT (S ≈ 200 μV/K per element, ~ 127 elements: S_total ≈ 25 mV/K, expect V ≈ S·ΔT).
- Maximum power when R_load ≈ R_internal (≈2.5 Ω).
- Efficiency η = P / (Q_in) expected 4-6%.

## Calculations
- Power: P = V * I  → check P = I² R as verification
- Efficiency: η = P / (k·A·ΔT/d) approximated; use measured heat input if available
- Plot P vs R for each ΔT

## Questions
1. Why does power peak at matched load?
2. How does heat sink performance affect ΔT maintenance?

## Sources of Error
- Thermocouple accuracy ±1K
- Contact thermal resistance
- Heat loss to ambient not accounted in η
