# Methods overview

The complete methods are described in the article and in Appendix E1 of its supplemental material. This page
summarizes how the main components map to the code.

## Study design

- Controlled computational study with synthetic patients and documents only.
- 48 base scenarios (16 per module), each with a clean variant; 43 also with a misleading-information variant
  (91 variants). Each of six agents completed every variant under three configurations (1638 episodes in run 1).
- Scenarios, reference standard, evaluator, safeguards, checker prompt and the prespecified per-agent analysis were
  fixed before the first main run (freeze on 4 October 2026). Changes after the freeze are listed in
  `docs/deviations.md`.

## Components

| Component | Code |
|---|---|
| Simulated environment and tools | `src/ragis/world.py`, `tools.py`, `werkzeugschemata.py`, `scenario.py` |
| Agent system prompt | `scripts/run_episodes.py` (`SYSTEMPROMPT`; English translation in Appendix E2) |
| Episode loop, revision budget (2 per blocked action), tool-call budget (40) | `src/ragis/episode.py` |
| Configuration C: standard system checks | `src/ragis/tools.py`, `guards.py` |
| Configuration E: 11 deterministic rules (E01–E11) | `src/ragis/guards.py` |
| Configuration D: LLM checker (codes D01–D07), checker prompt version 5 | `src/ragis/guards.py`, `llm_pruefer.py` |
| Evaluator: violations in eight integrity dimensions (V1–V8), severity, task success, block classification | `src/ragis/evaluator.py` |

## Analysis

- Unit of analysis: base scenario. Outcomes are averaged over a scenario's variants; risk differences between
  configurations are estimated within scenario with a stratified t-interval (Satterthwaite degrees of freedom,
  modules weighted equally).
- Prespecified: per-agent analysis (`analysis/original/20_hauptauswertung.py`).
- Exploratory: pooled analyses across agents and logistic GEE (`24_modellvergleich.py`), severity sensitivity
  analysis (`21_sensitivitaet_schweregrad.py`), workflow step of violations (`22_fehlerorte_workflow.py`),
  alternative LLM checker (`26_starker_pruefer.py`), free-text screen (`27_freitext_screening.py`).
- `analysis/reproduce_main_results.py` recomputes the main results from the released episode-level data.
