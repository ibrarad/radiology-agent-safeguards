"""Agentenadapter fuer echte Modell-APIs.

Drei Wege, eine Schnittstelle:
  AnthropicAgent          - offizielles anthropic-SDK (Claude)
  OpenAIKompatiblerAgent  - offizielles openai-SDK gegen JEDEN OpenAI-kompatiblen Endpunkt:
                            OpenAI selbst, Google Gemini (Compat-Endpunkt), Groq,
                            GitHub Models, oder ein lokaler vLLM-/Ollama-Server
  (SkriptierterAgent in agents.py bleibt der Offline-Weg)

SPERREN, die hier technisch durchgesetzt sind:
  - Ohne Kostenwaechter mit Obergrenze wird kein Aufruf ausgefuehrt.
  - Vor jedem Aufruf wird reserviert, danach der tatsaechliche Verbrauch gebucht.
  - Schluessel werden aus einer Datei mit Modus 0600 gelesen und NIE protokolliert.
  - Es wird immer genau EIN Werkzeugaufruf je Runde angefordert, damit die Schutzschicht
    jede Aktion einzeln pruefen kann.

REPRODUZIERBARKEIT - wichtige Einschraenkung:
  Auf den aktuellen Claude-Modellen (Opus 5, Sonnet 5 und die 4.6+-Familie) sind
  temperature/top_p/top_k nicht mehr setzbar; ein Wert dafuer wird mit HTTP 400 abgewiesen.
  Gesteuert wird ueber output_config.effort. Determinismus ist damit auch nominell nicht
  herstellbar. Das ist im Manuskript zu berichten (REFINE 3.1, 5.6).
"""
from __future__ import annotations

import json
import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .kosten import Kostengrenze, Kostenwaechter
from .tools import Aktionsanfrage


class ZugangGesperrt(RuntimeError):
    """Kein Schluessel, keine Obergrenze, oder die Freigabe fehlt."""


# --------------------------------------------------------------------------- Schluessel

def lies_schluessel(pfad: str | Path) -> str:
    """Liest einen Schluessel aus einer Umgebungsvariablen ("env:NAME") oder aus einer Datei mit
    Modus 0600. Gibt ihn NIE aus."""
    if isinstance(pfad, str) and pfad.startswith("env:"):
        name = pfad[4:]
        schluessel = os.environ.get(name, "").strip()
        if not schluessel:
            raise ZugangGesperrt(f"Umgebungsvariable {name} ist nicht gesetzt.")
        return schluessel
    p = Path(pfad)
    if not p.is_file():
        raise ZugangGesperrt(
            f"Keine Schluesseldatei unter {p}. Modell-APIs bleiben gesperrt.")
    modus = stat.S_IMODE(p.stat().st_mode)
    if modus & 0o077:
        raise ZugangGesperrt(
            f"Schluesseldatei {p} ist zu weit lesbar (Modus {modus:04o}). "
            f"Erforderlich: chmod 600.")
    schluessel = p.read_text(encoding="utf-8").strip()
    if not schluessel:
        raise ZugangGesperrt(f"Schluesseldatei {p} ist leer.")
    return schluessel


# --------------------------------------------------------------------------- Lokale Modelle

# Seit 27.09.2026: offene Modelle auf dem eigenen Server (Ollama), ohne API-Kosten, die Daten
# bleiben im Haus. Zwei Besonderheiten dieses Rechners bzw. von Ollama:
#   - Ein Netzwerk-Proxy lehnt Anfragen an localhost ab; lokale Server werden deshalb ohne die
#     Proxy-Umgebungsvariablen angesprochen.
#   - Ollama schneidet eine zu lange Eingabe STILLSCHWEIGEND auf die Kontextgrenze ab (Test vom
#     27.09.2026: 24.000 Tokens gesendet, 4.096 angekommen, Antwort leer). Deshalb eigene
#     Modellvarianten mit 64k Kontext und eine harte Pruefung: Erreicht die Eingabe die Grenze,
#     bricht der Aufruf ab, statt auf abgeschnittener Eingabe weiterzurechnen.
OLLAMA_URL = "http://localhost:11434/v1"
LOKALE_HOSTS = ("localhost", "127.0.0.1")


class KontextUeberlauf(RuntimeError):
    """Die Eingabe hat die Kontextgrenze des lokalen Modells erreicht."""


def ist_lokal(basis_url: str | None) -> bool:
    from urllib.parse import urlparse
    return bool(basis_url) and urlparse(basis_url).hostname in LOKALE_HOSTS


def lokaler_http_client():
    import httpx
    return httpx.Client(trust_env=False, timeout=900.0)


def pruefe_kontext(prompt_tokens: int | None, grenze: int | None) -> None:
    if grenze and (prompt_tokens or 0) >= grenze:
        raise KontextUeberlauf(
            f"Eingabe mit {prompt_tokens} Tokens hat die Kontextgrenze {grenze} erreicht - "
            "das lokale Modell haette abgeschnitten.")


# --------------------------------------------------------------------------- Werkzeugschemata

def werkzeugschemata_anthropic(schemata: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": s["name"], "description": s["beschreibung"],
             "input_schema": s["parameter"]} for s in schemata]


def werkzeugschemata_openai(schemata: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "function",
             "function": {"name": s["name"], "description": s["beschreibung"],
                          "parameters": s["parameter"]}} for s in schemata]


# --------------------------------------------------------------------------- Basis

@dataclass
class ApiAgentBasis:
    modellkennung: str
    systemprompt: str
    werkzeugschemata: list[dict[str, Any]]
    waechter: Kostenwaechter
    komponente: str = "agent"
    # 16000 statt 4096 (24.09.2026): Denk-Tokens zaehlen zur Ausgabe. Mit 4096 haette ein
    # Modell mit hohem Denkaufwand vor dem Werkzeugaufruf abgeschnitten werden koennen.
    max_tokens: int = 16000
    schaetzung_usd_je_aufruf: float = 0.05
    # Der Auftrag der Episode. Bis zum 24.09.2026 erreichte er die API-Agenten NIE: Claude
    # haette beim ersten Aufruf eine leere Nachrichtenliste geschickt, das OpenAI-Modell nur
    # den allgemeinen Systemtext gesehen.
    aufgabenprompt: str = ""
    protokoll: list[dict[str, Any]] = field(default_factory=list)
    ist_platzhalter: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.kennung = f"api:{self.modellkennung}"
        self._verlauf: list[dict[str, Any]] = []
        if self.waechter.obergrenze_usd is None:
            raise ZugangGesperrt(
                "Kostenwaechter ohne Obergrenze. Es wird kein Modellaufruf ausgefuehrt.")

    # ------------------------------------------------------------------
    def _beobachtung_als_werkzeugergebnis(self, beobachtung: dict[str, Any]) -> str:
        """Was der Agent nach einer Aktion zurueckbekommt - inkl. Schutz-Rueckmeldung."""
        teile: dict[str, Any] = {"ergebnis": beobachtung.get("ergebnis")}
        if beobachtung.get("rueckmeldung"):
            teile["hinweis_der_pruefschicht"] = beobachtung["rueckmeldung"]
        return json.dumps(teile, ensure_ascii=False, default=str)[:20000]

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        raise NotImplementedError

    def _auftrag(self) -> str:
        if not self.aufgabenprompt.strip():
            raise ValueError("API-Agent ohne Auftrag (aufgabenprompt) - die Episode waere "
                             "ohne Aufgabe gelaufen.")
        return self.aufgabenprompt


# --------------------------------------------------------------------------- Anthropic

class AnthropicAgent(ApiAgentBasis):
    """Claude ueber das offizielle anthropic-SDK, manuelle Werkzeugschleife."""

    def __init__(self, *args, schluesseldatei: str | Path | None = None,
                 effort: str = "high", client: Any = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.effort = effort
        if client is not None:          # Attrappe in Tests
            self._client = client
        else:
            import anthropic  # lokal importiert, damit der Offline-Betrieb ohne SDK laeuft
            schluessel = lies_schluessel(schluesseldatei) if schluesseldatei else None
            self._client = anthropic.Anthropic(api_key=schluessel) if schluessel \
                else anthropic.Anthropic()
        self._tools = werkzeugschemata_anthropic(self.werkzeugschemata)
        self._offener_tool_use_id: str | None = None

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        if beobachtung is not None and self._offener_tool_use_id:
            self._verlauf.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": self._offener_tool_use_id,
                "content": self._beobachtung_als_werkzeugergebnis(beobachtung)}]})
            self._offener_tool_use_id = None
        if not self._verlauf:
            self._verlauf.append({"role": "user", "content": self._auftrag()})

        marke = self.waechter.reserviere(self.komponente, self.schaetzung_usd_je_aufruf)
        beginn = time.perf_counter()
        try:
            antwort = self._client.messages.create(
                model=self.modellkennung,
                max_tokens=self.max_tokens,
                system=[{"type": "text", "text": self.systemprompt,
                         "cache_control": {"type": "ephemeral"}}],
                tools=self._tools,
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                output_config={"effort": self.effort},
                messages=self._verlauf,
                # Seit 26.09.2026: automatisches Zwischenspeichern des ganzen Verlaufs. Vorher
                # war nur der Systemtext markiert, und jeder Aufruf zahlte den wachsenden
                # Verlauf voll - bei 14 Aufrufen je Episode etwa das Dreifache. OpenAI
                # speichert automatisch zwischen (Teil 1: 93 % der Eingabe). Am Verhalten des
                # Modells aendert das nichts.
                cache_control={"type": "ephemeral"},
            )
        except Exception:
            self.waechter.gib_frei(marke)
            raise

        u = antwort.usage
        self.waechter.buche(
            marke,
            input_tokens=getattr(u, "input_tokens", 0),
            output_tokens=getattr(u, "output_tokens", 0),
            modellkennung=self.modellkennung,
            cache_lesen=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_schreiben=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        self.protokoll.append({
            "stop_reason": antwort.stop_reason,
            # Zurueckgemeldete Modellversion je Aufruf.
            "modell": getattr(antwort, "model", None),
            # Seit 26.09.2026: Dauer, angeforderter Aufwand und Zahl der Denkbloecke. Claude
            # meldet Denk-Tokens nicht getrennt, sie stecken in output_tokens.
            "dauer_s": round(time.perf_counter() - beginn, 2),
            "aufwand_angefordert": self.effort,
            "denkbloecke": sum(1 for b in antwort.content
                               if getattr(b, "type", None) in ("thinking", "redacted_thinking")),
            "usage": {k: getattr(u, k, None) for k in
                      ("input_tokens", "output_tokens",
                       "cache_read_input_tokens", "cache_creation_input_tokens")},
        })

        if antwort.stop_reason == "refusal":
            return None

        self._verlauf.append({"role": "assistant", "content": antwort.content})
        for block in antwort.content:
            if getattr(block, "type", None) == "tool_use":
                self._offener_tool_use_id = block.id
                # Werkzeugargumente immer parsen, nie per Zeichenkettenvergleich pruefen.
                args = block.input if isinstance(block.input, dict) else json.loads(block.input)
                return Aktionsanfrage(block.name, args)
        return None


# --------------------------------------------------------------------------- OpenAI-kompatibel

class OpenAIKompatiblerAgent(ApiAgentBasis):
    """Jeder OpenAI-kompatible Endpunkt: OpenAI, Gemini-Compat, Groq, GitHub Models, vLLM.

    Der einheitliche Weg ueber chat.completions ist bewusst gewaehlt: er funktioniert bei
    allen genannten Anbietern unveraendert und macht den Wechsel zu einem Konfigurationspunkt.
    """

    def __init__(self, *args, schluesseldatei: str | Path | None = None,
                 basis_url: str | None = None, reasoning_effort: str | None = None,
                 client: Any = None, kontextgrenze: int | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.reasoning_effort = reasoning_effort
        self.kontextgrenze = kontextgrenze
        if client is not None:          # Attrappe in Tests
            self._client = client
        elif ist_lokal(basis_url):      # lokaler Server: kein Schluessel, kein Proxy
            import openai
            self._client = openai.OpenAI(api_key="lokal", base_url=basis_url,
                                         http_client=lokaler_http_client())
        else:
            import openai
            schluessel = lies_schluessel(schluesseldatei) if schluesseldatei else \
                os.environ.get("RAGIS_API_SCHLUESSEL")
            if not schluessel:
                raise ZugangGesperrt("Kein Schluessel fuer den OpenAI-kompatiblen Endpunkt.")
            self._client = openai.OpenAI(api_key=schluessel, base_url=basis_url)
        self._tools = werkzeugschemata_openai(self.werkzeugschemata)
        self._verlauf = [{"role": "system", "content": self.systemprompt}]
        self._offene_tool_call_id: str | None = None

    def _zusatzparameter(self) -> dict[str, Any]:
        return {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}

    def _protokoll_zusatz(self, antwort: Any) -> dict[str, Any]:
        return {}

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        if beobachtung is not None and self._offene_tool_call_id:
            self._verlauf.append({
                "role": "tool", "tool_call_id": self._offene_tool_call_id,
                "content": self._beobachtung_als_werkzeugergebnis(beobachtung)})
            self._offene_tool_call_id = None
        if len(self._verlauf) == 1:
            self._verlauf.append({"role": "user", "content": self._auftrag()})

        zusatz: dict[str, Any] = self._zusatzparameter()

        marke = self.waechter.reserviere(self.komponente, self.schaetzung_usd_je_aufruf)
        beginn = time.perf_counter()
        try:
            antwort = self._client.chat.completions.create(
                model=self.modellkennung,
                messages=self._verlauf,
                tools=self._tools,
                tool_choice="auto",
                parallel_tool_calls=False,
                max_completion_tokens=self.max_tokens,
                **zusatz,
            )
        except Exception:
            self.waechter.gib_frei(marke)
            raise

        u = antwort.usage
        gecacht = 0
        details = getattr(u, "prompt_tokens_details", None)
        if details is not None:
            gecacht = getattr(details, "cached_tokens", 0) or 0
        self.waechter.buche(
            marke,
            input_tokens=max(0, (getattr(u, "prompt_tokens", 0) or 0) - gecacht),
            output_tokens=getattr(u, "completion_tokens", 0) or 0,
            modellkennung=self.modellkennung,
            cache_lesen=gecacht,
        )
        self.protokoll.append({
            "finish_reason": antwort.choices[0].finish_reason,
            "modell": getattr(antwort, "model", None),
            "dauer_s": round(time.perf_counter() - beginn, 2),
            "aufwand_angefordert": self.reasoning_effort,
            "usage": {"prompt_tokens": getattr(u, "prompt_tokens", None),
                      "completion_tokens": getattr(u, "completion_tokens", None),
                      "cached_tokens": gecacht},
            **self._protokoll_zusatz(antwort),
        })
        pruefe_kontext(getattr(u, "prompt_tokens", None), self.kontextgrenze)

        nachricht = antwort.choices[0].message
        self._verlauf.append(nachricht.model_dump(exclude_none=True))
        aufrufe = nachricht.tool_calls or []
        if not aufrufe:
            return None
        aufruf = aufrufe[0]
        self._offene_tool_call_id = aufruf.id
        args = json.loads(aufruf.function.arguments or "{}")
        return Aktionsanfrage(aufruf.function.name, args)


# --------------------------------------------------------------------------- OpenRouter

class OpenRouterAgent(OpenAIKompatiblerAgent):
    """Offene Spitzenmodelle ueber OpenRouter (seit 07.10.2026, Sekundaeranalyse).

    OpenRouter verteilt ein Modell auf viele Fremdanbieter mit unterschiedlicher Quantisierung.
    Fuer Reproduzierbarkeit wird genau ein Anbieter erzwungen (`anbieter_fest`, in der Regel der
    Originalhersteller), ohne Ausweichen. Denkaufwand ueber den einheitlichen `reasoning`-Parameter.
    Die von OpenRouter gemeldeten Kosten und der tatsaechliche Anbieter werden je Aufruf
    protokolliert; gebucht wird weiter ueber die eigene Preistabelle.
    """

    def __init__(self, *args, anbieter_fest: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not anbieter_fest:
            raise ValueError("OpenRouter: anbieter_fest muss gesetzt sein (Reproduzierbarkeit).")
        self.anbieter_fest = anbieter_fest

    def _zusatzparameter(self) -> dict[str, Any]:
        koerper: dict[str, Any] = {
            "provider": {"order": [self.anbieter_fest], "allow_fallbacks": False},
            "usage": {"include": True},
        }
        if self.reasoning_effort:
            koerper["reasoning"] = {"effort": self.reasoning_effort}
        return {"extra_body": koerper}

    def _protokoll_zusatz(self, antwort: Any) -> dict[str, Any]:
        u = antwort.usage
        return {"anbieter_gemeldet": getattr(antwort, "provider", None),
                "kosten_openrouter_usd": getattr(u, "cost", None)}


# --------------------------------------------------------------------------- OpenAI Responses-API

class OpenAIResponsesAgent(ApiAgentBasis):
    """OpenAI ueber die Responses-API (seit 24.09.2026).

    Noetig fuer Modelle wie gpt-6-sol: Laut Modellseite (23.09.2026) ruft es ueber Chat
    Completions Werkzeuge nur mit reasoning_effort=none auf - also ohne Denkaufwand, was es
    gegenueber Claude mit Denkaufwand unvergleichbar machte. Ueber die Responses-API sind
    Werkzeugaufrufe mit Denkaufwand moeglich.

    Die Responses-API meldet Cache-Schreibvorgaenge getrennt (input_tokens_details.
    cache_write_tokens); der Kostenwaechter bucht hier also exakt. Der Gesprächsverlauf wird
    ueber previous_response_id beim Anbieter gehalten; der Systemtext (instructions) wird
    bei jedem Aufruf mitgeschickt, weil er nicht uebernommen wird.
    """

    def __init__(self, *args, schluesseldatei: str | Path | None = None,
                 basis_url: str | None = None, reasoning_effort: str | None = "high",
                 client: Any = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.reasoning_effort = reasoning_effort
        if client is not None:          # Attrappe in Tests
            self._client = client
        else:
            import openai
            schluessel = lies_schluessel(schluesseldatei) if schluesseldatei else \
                os.environ.get("RAGIS_API_SCHLUESSEL")
            if not schluessel:
                raise ZugangGesperrt("Kein Schluessel fuer die OpenAI-Responses-API.")
            self._client = openai.OpenAI(api_key=schluessel, base_url=basis_url)
        self._tools = [{"type": "function", "name": s["name"], "description": s["beschreibung"],
                        "parameters": s["parameter"], "strict": False}
                       for s in self.werkzeugschemata]
        self._vorherige_id: str | None = None
        self._offene_call_id: str | None = None

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        if self._vorherige_id is None:
            eingabe: list[dict[str, Any]] = [{"role": "user", "content": self._auftrag()}]
        else:
            if beobachtung is None or not self._offene_call_id:
                return None
            eingabe = [{"type": "function_call_output", "call_id": self._offene_call_id,
                        "output": self._beobachtung_als_werkzeugergebnis(beobachtung)}]
            self._offene_call_id = None

        zusatz: dict[str, Any] = {}
        if self._vorherige_id:
            zusatz["previous_response_id"] = self._vorherige_id
        if self.reasoning_effort:
            zusatz["reasoning"] = {"effort": self.reasoning_effort}

        marke = self.waechter.reserviere(self.komponente, self.schaetzung_usd_je_aufruf)
        beginn = time.perf_counter()
        try:
            antwort = self._client.responses.create(
                model=self.modellkennung,
                instructions=self.systemprompt,
                input=eingabe,
                tools=self._tools,
                tool_choice="auto",
                parallel_tool_calls=False,
                max_output_tokens=self.max_tokens,
                **zusatz,
            )
        except Exception:
            self.waechter.gib_frei(marke)
            raise

        u = antwort.usage
        details = getattr(u, "input_tokens_details", None)
        gecacht = (getattr(details, "cached_tokens", 0) or 0) if details is not None else 0
        geschrieben = (getattr(details, "cache_write_tokens", 0) or 0) if details is not None else 0
        self.waechter.buche(
            marke,
            input_tokens=max(0, (getattr(u, "input_tokens", 0) or 0) - gecacht - geschrieben),
            output_tokens=getattr(u, "output_tokens", 0) or 0,
            modellkennung=self.modellkennung,
            cache_lesen=gecacht, cache_schreiben=geschrieben,
        )
        denk = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", None)
        self.protokoll.append({
            "status": getattr(antwort, "status", None),
            "modell": getattr(antwort, "model", None),
            # Seit 26.09.2026: Dauer und der vom Anbieter bestaetigte Denkaufwand (die Antwort
            # gibt die angewandte Einstellung zurueck) - im ersten Pilotteil fehlte beides.
            "dauer_s": round(time.perf_counter() - beginn, 2),
            "aufwand_angefordert": self.reasoning_effort,
            "aufwand_bestaetigt": getattr(getattr(antwort, "reasoning", None), "effort", None),
            "usage": {"input_tokens": getattr(u, "input_tokens", None),
                      "output_tokens": getattr(u, "output_tokens", None),
                      "cached_tokens": gecacht, "cache_write_tokens": geschrieben,
                      "reasoning_tokens": denk},
        })
        self._vorherige_id = antwort.id
        for element in antwort.output or []:
            if getattr(element, "type", None) == "function_call":
                self._offene_call_id = element.call_id
                return Aktionsanfrage(element.name, json.loads(element.arguments or "{}"))
        return None


# --------------------------------------------------------------------------- Fabrik

ANBIETER = {
    # kennung: (Klasse, Basis-URL oder None, Bemerkung)
    "anthropic": (AnthropicAgent, None, "offizielle Claude-API"),
    "openai": (OpenAIKompatiblerAgent, None, "offizielle OpenAI-API"),
    "openai_responses": (OpenAIResponsesAgent, None,
                         "offizielle OpenAI-API ueber die Responses-API (z. B. gpt-6-sol)"),
    "gemini": (OpenAIKompatiblerAgent,
               "https://generativelanguage.googleapis.com/v1beta/openai/",
               "Google Gemini ueber den OpenAI-kompatiblen Endpunkt"),
    "groq": (OpenAIKompatiblerAgent, "https://api.groq.com/openai/v1",
             "Groq, freie Stufe mit engem Ratenlimit"),
    "github": (OpenAIKompatiblerAgent, "https://models.github.ai/inference",
               "GitHub Models"),
    "lokal": (OpenAIKompatiblerAgent, "http://localhost:8000/v1",
              "lokaler vLLM-Server"),
    "openrouter": (OpenRouterAgent, "https://openrouter.ai/api/v1",
                   "OpenRouter, Anbieter fest (anbieter_fest), ohne Ausweichen"),
    "ollama": (OpenAIKompatiblerAgent, OLLAMA_URL,
               "lokaler Ollama-Server auf diesem Rechner, keine API-Kosten"),
}


def baue_api_agenten(anbieter: str, modellkennung: str, systemprompt: str,
                     werkzeugschemata: list[dict[str, Any]], waechter: Kostenwaechter,
                     schluesseldatei: str | Path | None = None,
                     **kwargs) -> ApiAgentBasis:
    if anbieter not in ANBIETER:
        raise ValueError(f"unbekannter Anbieter '{anbieter}'. "
                         f"Bekannt: {', '.join(sorted(ANBIETER))}")
    klasse, basis_url, _ = ANBIETER[anbieter]
    gemeinsam = dict(modellkennung=modellkennung, systemprompt=systemprompt,
                     werkzeugschemata=werkzeugschemata, waechter=waechter,
                     schluesseldatei=schluesseldatei)
    if klasse in (OpenAIKompatiblerAgent, OpenAIResponsesAgent, OpenRouterAgent):
        # Eigene Basis-URL aus der Konfiguration, z. B. ein zweiter lokaler Ollama-Server
        #
        gemeinsam["basis_url"] = kwargs.pop("basis_url", None) or basis_url
    return klasse(**gemeinsam, **kwargs)
