"""DARWIN Meta-Engine — Discovery Loop

The autonomous edge-hunting pipeline:

    DATA ADAPTERS → ANOMALY SCANNERS → global BH-FDR control →
    EXPLORER (LLM turns verified anomalies into falsifiable hypotheses) →
    Discovery records enter the library as CANDIDATE

Design rules:
- Scanners are DETERMINISTIC. They read real data and emit anomalies with
  verified statistics (Welch t vs matched control, sample sizes, windows).
- Multiple-testing control is GLOBAL across the whole run: every test from
  every scanner counts as a trial, one Benjamini–Hochberg step-up decides
  what survives. A p-value quoted without its trials_tested is worthless.
- The Explorer LLM only ever sees verified anomaly records. It frames
  hypotheses; it never asserts findings.
- If the LLM is unavailable, a deterministic template frames the hypothesis
  instead — discovery does not depend on the model being up.
"""
