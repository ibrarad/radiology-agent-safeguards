# Glossary of German identifiers

The code base uses German identifiers, comments and messages. This glossary translates the most important terms.

## Modules in `src/ragis/`

| Module | Content |
|---|---|
| `model.py` | Data model: documents, statements, status values, events, vocabulary of finding codes |
| `world.py` | Simulated information system (documents, examinations, events, visibility) |
| `tools.py`, `werkzeugschemata.py` | Agent tools and their JSON schemas |
| `scenario.py` | Loads a scenario variant and builds the simulated world |
| `episode.py` | Runs one episode: tool calls, safeguard gate, revision budget, recording |
| `guards.py` | Safeguard configurations C, E and D; the 11 deterministic rules (E01–E11) |
| `llm_pruefer.py` | LLM checker, including the checker prompt (version 5) and the structured output format |
| `llm_pruefer_openrouter.py` | Alternative checker accessed through OpenRouter (exploratory analysis) |
| `semantic.py` | Semantic checker interface for configuration D (deterministic placeholder for tests and helper rules such as explicit corrections) |
| `evaluator.py` | Independent deterministic evaluator (violations, severity, task success, block classification) |
| `api_adapter.py` | Adapters for the agent models (Anthropic, OpenAI, OpenRouter, local OpenAI-compatible servers) |
| `agents.py` | Scripted deterministic agent for functional tests and scripted walk-throughs |
| `kosten.py` | Cost guard with reservation before every model call |
| `angriffe.py` | Prompt-injection variants used only in the development-phase security test |
| `begriffe.py` | Public terminology: keywords per finding code |
| `regelbasiert.py` | Rule-based reference solution without LLM (development only) |
| `audit.py` | Stratified sampling for a physician episode audit (not used in the article) |
| `common.py` | Shared utilities (identifiers, canonical JSON, checksums, simulation time, access guard for the reference standard) |

## Terms

| German | English |
|---|---|
| Abschluss, `melde_abschluss` | completion, completion report |
| Arbeitsartefakt, Artefakt | work product |
| Arm (C, E, D) | safeguard configuration (permissions only, deterministic rules, rules plus LLM checker) |
| Aufgabenpolitik | task policy |
| Aufwand | reasoning effort |
| Aussage | structured statement |
| Befund, Befundcode | finding or report, finding code |
| Belegstelle | quoted passage of a source |
| berechtigt / unnötig (Blockade) | justified / unnecessary (block) |
| Bewerter | evaluator |
| Blockade, blockiert | block, blocked |
| Boardvorlage | tumor board draft |
| D-Logik | decision logic of configuration D |
| Ereignis | documented event (for example communication, examination performed) |
| Falle, Faktenmanipulation, `--fm` | misleading information, misleading-information variant |
| Fallsatz | scenario set |
| Freigabe | (report) release; in run configurations: cost approval |
| Gewissheit | certainty |
| Gold, Goldreferenz | reference standard |
| hoch / moderat / gering | high / medium / low (severity) |
| Klärungsauftrag, Klärungsbedarf | clarification request |
| Kommunikationsübersicht | communication overview |
| Korrekturbudget | revision budget (two revisions per blocked action) |
| Kostengrenze, Kostenwächter | cost limit, cost guard |
| Lauf | run |
| Nachverfolgung | follow-up |
| Polarität | polarity (present or absent) |
| Prüfer, Prüferauftrag | (LLM) checker, checker prompt |
| Quelle | source document |
| sauber | clean (variant) |
| Schutzschicht | safeguard layer |
| Sichtbarkeit | visibility to the referrer |
| Stufe, Schwere | severity |
| Trockenlauf / echt | dry run / real run |
| Verletzung | violation |
| Werkzeug, Werkzeugaufruf | tool, tool call |
| Wiederholung | repetition (run) |
| Zeitbezug | time reference |
| Zuweiser | referrer |
