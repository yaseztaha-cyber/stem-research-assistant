# Thermoelectric Energy - Study Notes

## Overview
Thermoelectric effect converts thermal gradient to electrical energy.

## Key Concepts

### Seebeck Effect
- When two different conductors are joined and junctions are at different temperatures, voltage is generated.
- Equation: V = S * ΔT
  - V = voltage [V]
  - S = Seebeck coefficient [V/K]
  - ΔT = temperature difference [K]

### Thermoelectric Generator (TEG)
- Made of p-type and n-type semiconductor legs (often Bi2Te3).
- Hot side and cold side create ΔT.

## Key Equations

- Ohm's Law: V = I * R
  - V voltage (V), I current (A), R resistance (Ω)
- Power: P = V * I
  - P power (W)
- Efficiency: η = Pout / Pin
  - η efficiency (dimensionless or %)
- Heat: Q = m * c * ΔT
  - Q heat (J), m mass (kg), c specific heat (J/kg·K), ΔT temperature difference (K)

## Experimental Insights (from paper)
- At ΔT = 120K, V ≈ 3.3 V, I ≈ 1.27 A, P ≈ 4.2 W
- Efficiency 5.2% at that point.
- ZT = 0.95 figure of merit.
- Output increased ~14% (normalized) when ΔT 100K -> 120K

## Common Mistakes
- Confusing Seebeck coefficient with conductivity
- Forgetting unit verification: V/K * K = V correct; W = V*A
- Assuming linear behavior at very high ΔT (losses increase)

## Research Questions to Explore
- How does nanostructuring affect ZT?
- What heat sink design maximizes ΔT in practice?
