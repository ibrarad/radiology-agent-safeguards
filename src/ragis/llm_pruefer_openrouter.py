"""LLM-Pruefer ueber OpenRouter (Zusatzanalyse "starker Pruefer", 11.10.2026).

Eigene Datei, damit der eingefrorene Pruefer (llm_pruefer.py, FREEZE_HAUPTTEST.json) unveraendert
bleibt. Auftrag, Antwortformat, Auswertung der Antwort und Ausfallregeln sind die des
eingefrorenen LlmPruefer; neu ist nur der Zugang:
  - OpenRouter, Anfrage fest an den Originalhersteller gebunden, ohne Ausweichen
    (wie OpenRouterAgent in api_adapter.py)
  - Denkaufwand ueber den einheitlichen 'reasoning'-Parameter
  - Systemauftrag mit cache_control, damit er bei Anthropic zwischengespeichert wird
  - Verbrauch einschliesslich Cache-Lesen und -Schreiben aus der OpenRouter-Meldung
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .kosten import Kostenwaechter
from .llm_pruefer import ANTWORTSCHEMA, LlmPruefer

OPENROUTER_URL = "https://openrouter.ai/api/v1"


class OpenRouterPruefer(LlmPruefer):

    def __init__(self, modellkennung: str, waechter: Kostenwaechter, *,
                 schluesseldatei: str | Path, anbieter_fest: str = "anthropic",
                 aufwand: str | None = "high", strukturiert: bool = False,
                 **kwargs: Any) -> None:
        from .api_adapter import lies_schluessel
        import openai
        client = openai.OpenAI(api_key=lies_schluessel(schluesseldatei), base_url=OPENROUTER_URL)
        super().__init__("openai", modellkennung, waechter, client=client, aufwand=aufwand,
                         strukturiert=False, **kwargs)
        self.anbieter = "openrouter"
        self.anbieter_fest = anbieter_fest
        self.strukturiert = strukturiert
        self.kennung = (f"llm:openrouter[{anbieter_fest}]:{modellkennung}"
                        f":auftrag-{self.auftrag_version}:aufwand-{aufwand}"
                        + (":strukturiert" if strukturiert else ""))
        self.kosten_openrouter_usd = 0.0
        self.anbieter_gemeldet: set[str] = set()

    def _rufe(self, nachricht: str) -> tuple[str, str, dict[str, int]]:
        koerper: dict[str, Any] = {
            "provider": {"order": [self.anbieter_fest], "allow_fallbacks": False},
            "usage": {"include": True},
        }
        if self.aufwand:
            koerper["reasoning"] = {"effort": self.aufwand}
        zusatz: dict[str, Any] = {}
        if self.strukturiert:
            zusatz["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "pruefbefund", "schema": ANTWORTSCHEMA, "strict": True}}
        antwort = self._client.chat.completions.create(
            model=self.modellkennung,
            messages=[{"role": "system", "content": [
                          {"type": "text", "text": self.systemprompt,
                           "cache_control": {"type": "ephemeral"}}]},
                      {"role": "user", "content": nachricht}],
            max_tokens=self.max_tokens,
            extra_body=koerper,
            **zusatz,
        )
        wahl = antwort.choices[0]
        u = antwort.usage
        details = getattr(u, "prompt_tokens_details", None)
        lesen = (getattr(details, "cached_tokens", 0) or 0) if details is not None else 0
        schreiben = (getattr(details, "cache_write_tokens", 0) or 0) if details is not None else 0
        kosten = getattr(u, "cost", None)
        if kosten:
            self.kosten_openrouter_usd += float(kosten)
        gemeldet = getattr(antwort, "provider", None)
        if gemeldet:
            self.anbieter_gemeldet.add(str(gemeldet))
        return (wahl.message.content or ""), (wahl.finish_reason or ""), {
            "input_tokens": max(0, (getattr(u, "prompt_tokens", 0) or 0) - lesen - schreiben),
            "output_tokens": getattr(u, "completion_tokens", 0) or 0,
            "cache_lesen": lesen, "cache_schreiben": schreiben,
        }
