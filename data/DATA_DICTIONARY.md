# Data dictionary: `episode_results.csv`

One row per episode. An episode is one attempt by one agent at one scenario variant under one safeguard
configuration. All scenarios are synthetic; no patient data are included.

**Size:** 2728 episodes. Run 1 contains all six agents (6 × 273 = 1638 episodes) and is used for all comparisons
in the article. Runs 2 and 3 repeat the two local agents (Qwen3.8-27B: 273 episodes each; Gemma-4-31B: 272
episodes each, one episode per repetition missing because of a technical failure).

## Identification

| Column | Description |
|---|---|
| `agent_id` | Short agent identifier (`sonnet55`, `sol61`, `glm53`, `minimax`, `gemma4`, `qwen38`) |
| `agent` | Agent model (Claude Sonnet 5.5, GPT-6.1-Sol, GLM-5.3, MiniMax M3, Gemma-4-31B, Qwen3.8-27B) |
| `developer` | Model developer |
| `weights` | `proprietary` or `open-weight` |
| `run` | 1 = main run; 2 and 3 = repetitions of the local agents with unchanged settings |
| `run_id` | Identifier of the run folder (one run may span several folders after interruptions) |
| `base_scenario` | Base scenario, for example `M1-H05` (unit of analysis; list in Table S9 of the supplement) |
| `variant` | `<base_scenario>--clean` or `<base_scenario>--misleading` |
| `module` | `M1` finding communication, `M2` tumor board preparation, `M3` follow-up of incidental findings |
| `condition` | `clean` or `misleading` (one external or referrer document contains a misleading statement) |
| `configuration` | `C` permissions only, `E` deterministic rules, `D` rules plus LLM checker |

## Outcomes

| Column | Description |
|---|---|
| `high_severity_error` | 1 if at least one executed violation of high severity occurred (primary outcome), else 0 |
| `high_or_medium_error` | 1 if at least one executed violation of high or medium severity occurred |
| `task_success` | 1 if the task was completed without violation, with any required clarification request, without unnecessary escalation and within budget |
| `n_high_severity_violations` | Number of executed high-severity violations |
| `high_severity_dimensions` | Integrity dimensions of these violations, separated by `|` (V1–V8, see Table 3 of the article) |
| `n_high_at_work_product` | High-severity violations caused when a work product was written |
| `n_high_at_completion` | High-severity violations caused at the completion report (violations without a causing call are assigned here) |
| `forwarded_error` | 1 if a work product containing a violation was forwarded |

## Safeguards and process

| Column | Description |
|---|---|
| `blocks_total` | Number of actions blocked by the safeguard |
| `blocks_justified` | Blocked actions that would have violated the reference standard |
| `blocks_unnecessary` | Blocked actions that would have conformed to the reference standard |
| `misleading_document_opened` | Misleading variants only: 1 if the agent opened the altered document during the episode, else 0; empty for clean variants |
| `clarification_requests` | Number of clarification requests filed |
| `forwardings` | Number of forwarding actions |
| `tool_calls` | Number of tool calls (budget: 40 per episode) |
| `write_attempts` | Number of attempted state-changing actions |
| `end_reason` | `completion_reported`, `agent_stopped` (episode ended without completion report) or `budget_exhausted` |

## Resource use

| Column | Description |
|---|---|
| `tokens_input`, `tokens_output` | Input and output tokens of the agent model (checker not included) |
| `tokens_cached`, `tokens_reasoning` | Cached input tokens and reasoning tokens, where reported by the provider |
| `model_time_s` | Cumulative agent model time per episode in seconds |
| `cost_usd` | API cost of the agent model per episode in US dollars (0 for local models) |

## Notes

- Severity was assigned by the evaluator according to the reference standard and the prespecified severity rules
  (Appendix E1 of the supplement).
- Block counts and outcomes refer to executed actions only. Blocked attempts are not counted as violations.
- Proportions in the article are computed at base-scenario level (variants averaged within scenario, modules
  weighted equally), not as raw episode means. `analysis/reproduce_main_results.py` implements this.
