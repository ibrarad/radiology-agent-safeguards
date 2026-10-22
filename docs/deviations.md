# Deviations from the frozen plan

Scenarios, reference standard, evaluator, safeguards, checker prompt (version 5) and the prespecified per-agent
analysis were frozen on 4 October 2026, before the first main run. None of these components was changed
afterwards. The following changes and additions occurred after the freeze. Analyses added after the freeze
are reported as exploratory in the article.

| Date (2026) | Change | Classification |
|---|---|---|
| 6–10 Oct | Five further agents were added after the first main run had been completed and analyzed: GPT-6.1-Sol, Claude Sonnet 5.5, Gemma-4-31B, GLM-5.3 and MiniMax M3. They used the same frozen scenarios, reference standard, evaluator, safeguards and checker. For Gemma-4-31B as agent, checker and agent are the same model. | Protocol extension |
| 8 Oct | All six agents are reported as equally weighted main results, analyzed per agent with the unchanged prespecified method, instead of one primary agent. | Change in reporting |
| 6–10 Oct | Runs that stopped at a cost limit or after exhausted API credits were continued with unchanged settings. Incomplete runs that had been restarted from the beginning, and one run started in parallel by mistake, were discarded and not analyzed. One GLM-5.3 episode with a technical failure was repeated. | Run management |
| 7 Oct | Severity sensitivity analysis with alternative severity rules, defined after viewing the results; the prespecified analysis was not changed. | Post hoc, exploratory |
| 8 Oct | Pooled analyses across agents (scenario means across agents, logistic GEE with configuration-by-agent interaction) and localization of high-severity violations to the workflow step. | Post hoc, exploratory |
| 8–9 Oct | Two repetitions of the two local agents with unchanged settings and default sampling to assess run-to-run variability. | Post hoc, exploratory |
| 11–12 Oct | Repetition of configuration D for the two local agents with Claude Sonnet 5.5 as alternative checker. A new adapter file (`src/ragis/llm_pruefer_openrouter.py`) was added; the frozen checker code was not changed. | Post hoc, exploratory |
| 17 Oct | Screen of the optional free text of work products for high-severity errors not captured by the structured statements. | Post hoc, exploratory |
