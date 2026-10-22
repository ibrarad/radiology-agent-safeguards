"""Agentenadapter.

SkriptierterAgent  - deterministischer Agent fuer die technischen Funktionstests.
                     KEIN Studienarm, KEINE Evidenz ueber Modellverhalten.
ApiAgent           - werkzeugnutzender Agent ueber eine offizielle Modell-API.
                     Erst nach dokumentiertem Zugang und Kostenobergrenze aktiv.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .tools import Aktionsanfrage


class Agent(Protocol):
    kennung: str
    ist_platzhalter: bool

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        ...


@dataclass
class Schritt:
    werkzeug: str
    argumente: dict[str, Any]
    # Verhalten, wenn die Schutzschicht die Aktion nicht ausfuehrt:
    #   "weiter"      - naechster Schritt (Agent gibt auf)
    #   "wiederholen" - denselben Schritt erneut (loest das Korrekturbudget aus)
    #   "ersatz"      - fuehre 'ersatzschritt' aus
    bei_zurueckweisung: str = "weiter"
    ersatzschritt: "Schritt | None" = None
    kommentar: str = ""


class SkriptierterAgent:
    """Deterministischer Agent. Bildet ein vorab festgelegtes Verhalten ab.

    Dient ausschliesslich dazu, Simulator, Schutzschichten und Bewerter zu testen.
    Er trifft keine Entscheidungen und ist kein Modell.
    """

    ist_platzhalter = True

    def __init__(self, plan: list[Schritt], kennung: str = "skriptiert-v0.1") -> None:
        self.kennung = kennung
        self.plan = plan
        self._index = 0
        self._ersatz_offen: Schritt | None = None
        self._letzte_nicht_ausgefuehrt = False

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        if beobachtung is not None:
            self._letzte_nicht_ausgefuehrt = not beobachtung.get("ausgefuehrt", True)

        if self._ersatz_offen is not None:
            schritt = self._ersatz_offen
            self._ersatz_offen = None
            return Aktionsanfrage(schritt.werkzeug, dict(schritt.argumente))

        if self._letzte_nicht_ausgefuehrt and self._index > 0:
            vorher = self.plan[self._index - 1]
            self._letzte_nicht_ausgefuehrt = False
            if vorher.bei_zurueckweisung == "wiederholen":
                return Aktionsanfrage(vorher.werkzeug, dict(vorher.argumente))
            if vorher.bei_zurueckweisung == "ersatz" and vorher.ersatzschritt is not None:
                s = vorher.ersatzschritt
                return Aktionsanfrage(s.werkzeug, dict(s.argumente))

        if self._index >= len(self.plan):
            return None
        schritt = self.plan[self._index]
        self._index += 1
        return Aktionsanfrage(schritt.werkzeug, dict(schritt.argumente))


@dataclass
class ApiAgent:
    """Werkzeugnutzender Agent ueber eine offizielle Modell-API.

    Nicht aktiv, solange kein dokumentierter Zugang und keine ausdrueckliche Kostenobergrenze
    vorliegen.
    """
    modellkennung: str
    systemprompt: str
    werkzeugschemata: list[dict[str, Any]]
    api_client: Any = None
    temperatur: float = 0.0
    ist_platzhalter: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.kennung = f"api:{self.modellkennung}"

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        if self.api_client is None:
            raise RuntimeError(
                "ApiAgent ohne Client aufgerufen. Modell-APIs sind gesperrt, solange kein "
                "dokumentierter Zugang und keine Kostenobergrenze vorliegen."
            )
        raise NotImplementedError(
            "Der API-Aufrufpfad wird erst nach Freigabe von Zugang und Budget implementiert."
        )
