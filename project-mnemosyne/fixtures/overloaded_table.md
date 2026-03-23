# Metric Reference Table

The table below documents all computed metrics, their formulas, thresholds, and recommended actions.

| Metric | Formula | Fast Mode | Precise Mode | Weight | Low Threshold | High Threshold | Unit | Recommended Action |
|--------|---------|-----------|--------------|--------|---------------|----------------|------|--------------------|
| L_txt | RD * ln(1+TD) | Ergo rules | Full NLP | 0.45 | 0.3 | 0.7 | normalized | Split paragraphs |
| L_vis | E/N | Edge ratio | Layout engine | 0.30 | 0.2 | 0.6 | normalized | Simplify diagrams |
| L_spa | IU distance | Ordinal | Browser layout | 0.25 | 0.15 | 0.5 | normalized | Reorder sections |
| C_load | Weighted sum | All modes | All modes | 1.0 | 0.25 | 0.65 | normalized | See sub-metrics |
| friction_index | C_load * 100 | All modes | All modes | — | 25 | 65 | integer | Reduce C_load |

> **Note:** This table has 9 columns, exceeding the ergonomic limit of 8. It should be split into focused sub-tables.
