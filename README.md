# Safeguarding Agentic AI in Radiology Workflows

Code and episode-level data for the study **"Safeguarding Agentic AI in Radiology Workflows: A Multimodel
Evaluation of Rule-based and Large Language Model–based Verification"**

Six tool-using large language model (LLM) agents completed simulated radiology documentation tasks
(finding communication, tumor board preparation, follow-up of incidental findings) under three safeguard
configurations: permissions only (C), deterministic rules (E), and rules plus an LLM checker (D). A deterministic
evaluator scored every executed statement against a radiologist-defined reference standard.

## Contents

| Path | Content |
|---|---|
| `src/ragis/` | Simulated environment and agent tools, safeguards (11 deterministic rules, LLM checker with checker prompt v5), task policies, independent evaluator, model adapters |
| `scripts/run_episodes.py` | Runs agent episodes (dry run by default) and scores them |
| `config/run_settings.json` | Model versions, providers and settings of the main runs |
| `config/run_example.json` | Example run configuration for `scripts/run_episodes.py` |
| `data/episode_results.csv` | One row per episode (2728 episodes: 1638 first-run episodes plus two repetitions of the two local agents) |
| `data/DATA_DICTIONARY.md` | Description of all columns |
| `analysis/reproduce_main_results.py` | Reproduces the main results of the manuscript from `data/episode_results.csv` |
| `analysis/original/` | Original analysis scripts as used for the manuscript (require the data available on request) |
| `docs/` | Methods overview, deviations after the freeze, glossary of German identifiers |

**Not included** (available from the corresponding author on reasonable request): scenario files, reference
standard, scenario generator scripts and full episode transcripts. Scenario files carry a canary string so that
shared copies can be detected and excluded from model training data.

## Reproducing the main results

Requires Python 3.12 (tested with 3.9–3.12) and the packages in `requirements.txt`.

```bash
pip install -r requirements.txt
python analysis/reproduce_main_results.py
```

The script recomputes from the released data, among others, the proportions of episodes with a high-severity
error per agent and configuration, the prespecified risk differences per agent, the exploratory pooled risk
differences (for example −6.2 percentage points, 95% CI: −9.5, −3.0, for rules plus LLM checker versus
permissions only), the GEE odds ratios and interaction test, the localization of high-severity violations, document
access and block precision.

## Running episodes

`scripts/run_episodes.py` needs the scenario files and reference standard (on request) in `cases/main_sealed/` and
`gold/main_sealed/`, an LLM checker served through an OpenAI-compatible endpoint (for example Ollama) and API keys
set as environment variables (for example `ANTHROPIC_API_KEY`, referenced as `env:ANTHROPIC_API_KEY` in the
configuration). Without `--echt` the script performs a dry run and calls no model.

```bash
python scripts/run_episodes.py --konfig config/run_example.json
```

## Notes on the code

- Identifiers, comments and messages are in German. `docs/glossary.md` translates the main terms.
- Compared with the version frozen before the main runs (4 October 2026), only comments and message texts were
  edited to remove internal references, and API keys can now be read from environment variables. The program logic
  is unchanged; this was verified by comparing the syntax trees of all modules.
- Detailed methods are given in Appendix E1 of the supplemental material of the article; `docs/methods.md`
  summarizes how they map to the code.

## Licenses

Code: MIT License (`LICENSE`). Data in `data/`: Creative Commons Attribution 4.0 International (`data/LICENSE`).

## Citation

Please cite the article (reference will be added after publication).

## Contact

Author and contact information will be added after peer review.
