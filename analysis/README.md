# Analysis

## `reproduce_main_results.py`

Recomputes the main results of the article from `data/episode_results.csv` (first run only). It uses the same
interval method as the prespecified analysis and the same GEE specification as the exploratory pooled model.

```bash
python analysis/reproduce_main_results.py --out report.md
```

## `original/`

The original analysis scripts used for the manuscript, with comments and messages in German. They read the full
episode transcripts, scenario files and reference standard, which are available from the corresponding author on
reasonable request, and are provided for transparency.

| Script | Analysis |
|---|---|
| `20_hauptauswertung.py` | Prespecified per-agent analysis (frozen before the main runs) |
| `21_sensitivitaet_schweregrad.py` | Severity sensitivity analysis (post hoc) |
| `22_fehlerorte_workflow.py` | Workflow step of high-severity violations (post hoc) |
| `23_datensatz_alle_modelle.py` | Builds the episode-level data set (source of `data/episode_results.csv`, with German column names) |
| `24_modellvergleich.py` | Pooled comparisons and logistic GEE (post hoc) |
| `26_starker_pruefer.py` | Alternative LLM checker (post hoc) |
| `27_freitext_screening.py` | Free-text screen (post hoc) |
