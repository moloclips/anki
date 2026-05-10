METR Time Horizons

Files in this folder:

- `benchmark_results_1_0.yaml`: public TH 1.0 benchmark results scraped from METR.
- `benchmark_results_1_1.yaml`: public TH 1.1 benchmark results scraped from METR.
- `time_horizons_combined.csv`: flattened table combining both public benchmark YAMLs.

Summary:

- TH 1.0 publishes 33 model entries.
- TH 1.1 publishes 25 model entries.
- Combined raw rows across both public releases: 58.
- After normalizing TH 1.1 model ids by removing the `_inspect` suffix, the union is 42 model ids and the overlap is 16.

Confidence intervals:

- METR does not publish 90% confidence intervals in these benchmark result files.
- METR publishes 95% confidence intervals for both p50 and p80 horizons.
- In the public YAML/CSV, these appear as:
  - `p50_estimate`, `p50_ci_low`, `p50_ci_high`
  - `p80_estimate`, `p80_ci_low`, `p80_ci_high`
- In the analysis code, these are sourced from `p50q0.025`, `p50q0.975`, `p80q0.025`, and `p80q0.975`.

Coverage:

- Every model row in both public benchmark YAMLs has:
  - a published p50 estimate plus lower/upper CI
  - a published p80 estimate plus lower/upper CI
- No public model rows in these two files are missing those fields.

Primary sources used:

- METR time horizons page: https://metr.org/time-horizons/
- METR analysis repo: https://github.com/METR/eval-analysis-public
