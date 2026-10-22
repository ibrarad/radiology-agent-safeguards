"""Kostenerfassung, kumulative Kostengrenze und Wiederholungsregeln.

Kernpunkte der Vorgabe, die hier umgesetzt sind:
  - kumulative Kostengrenzen EINSCHLIESSLICH reservierter Kosten laufender Aufrufe;
  - begrenzte Retry-Regeln, Rate-Limit-Behandlung und Kennzeichnung jeder Wiederholung;
  - Replay gespeicherter Antworten wird NICHT erneut als API-Verbrauch verbucht;
  - keine Speicherung geheimer Schluessel.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


class Kostengrenze(RuntimeError):
    """Wird geworfen, bevor ein Aufruf die vereinbarte Obergrenze ueberschreiten wuerde."""


@dataclass(frozen=True)
class Preis:
    modellkennung: str
    input_pro_mio: float
    output_pro_mio: float
    cache_lesen_pro_mio: float = 0.0
    cache_schreiben_pro_mio: float = 0.0
    stand: str = ""
    quelle: str = ""
    # False, wenn der Preis am Stichtag nicht an der Anbieterseite belegt werden konnte.
    # Die Startpruefung des Piloten verweigert dann den echten Lauf (seit 23.09.2026).
    belegt: bool = True

    def berechne(self, input_tokens: int, output_tokens: int,
                 cache_lesen: int = 0, cache_schreiben: int = 0) -> float:
        return (input_tokens / 1e6 * self.input_pro_mio
                + output_tokens / 1e6 * self.output_pro_mio
                + cache_lesen / 1e6 * self.cache_lesen_pro_mio
                + cache_schreiben / 1e6 * self.cache_schreiben_pro_mio)


@dataclass
class Verbrauch:
    aufrufe: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_lesen_tokens: int = 0
    cache_schreiben_tokens: int = 0
    usd: float = 0.0
    wiederholungen: int = 0
    replays: int = 0            # aus dem Speicher beantwortet, kein API-Verbrauch

    def als_dict(self) -> dict[str, Any]:
        return {
            "aufrufe": self.aufrufe, "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_lesen_tokens": self.cache_lesen_tokens,
            "cache_schreiben_tokens": self.cache_schreiben_tokens,
            "usd": round(self.usd, 4), "wiederholungen": self.wiederholungen,
            "replays": self.replays,
        }


class Kostenwaechter:
    """Kumulative Kostengrenze mit Reservierung fuer laufende Aufrufe.

    Ablauf je Aufruf:
        marke = waechter.reserviere("agent", geschaetzte_kosten)
        ... API-Aufruf ...
        waechter.buche(marke, tatsaechliche Tokenzahlen)
      oder bei Fehlschlag:
        waechter.gib_frei(marke)

    Die Reservierung verhindert, dass mehrere gleichzeitig laufende Aufrufe die Grenze
    gemeinsam ueberschreiten, obwohl jeder einzeln noch hineinpasst.
    """

    def __init__(self, obergrenze_usd: float | None,
                 preise: dict[str, Preis] | None = None,
                 warnschwelle: float = 0.8) -> None:
        if obergrenze_usd is not None and obergrenze_usd <= 0:
            raise ValueError("Obergrenze muss positiv sein oder None (= gesperrt)")
        self.obergrenze_usd = obergrenze_usd
        self.preise = preise or {}
        self.warnschwelle = warnschwelle
        self._sperre = threading.Lock()
        self._reserviert: dict[int, tuple[str, float]] = {}
        self._naechste_marke = 1
        self.je_komponente: dict[str, Verbrauch] = {}
        self.warnung_ausgegeben = False

    # ------------------------------------------------------------------
    @property
    def gebucht_usd(self) -> float:
        return sum(v.usd for v in self.je_komponente.values())

    @property
    def reserviert_usd(self) -> float:
        return sum(betrag for _, betrag in self._reserviert.values())

    @property
    def belegt_usd(self) -> float:
        """Gebucht plus reserviert - der fuer die Grenzpruefung massgebliche Wert."""
        return self.gebucht_usd + self.reserviert_usd

    @property
    def rest_usd(self) -> float | None:
        if self.obergrenze_usd is None:
            return 0.0
        return max(0.0, self.obergrenze_usd - self.belegt_usd)

    def _verbrauch(self, komponente: str) -> Verbrauch:
        return self.je_komponente.setdefault(komponente, Verbrauch())

    # ------------------------------------------------------------------
    def reserviere(self, komponente: str, geschaetzte_usd: float) -> int:
        """Reserviert Budget. Wirft Kostengrenze, bevor die Grenze ueberschritten wuerde."""
        if self.obergrenze_usd is None:
            raise Kostengrenze(
                "Es ist keine Kostenobergrenze hinterlegt. Modell-APIs bleiben gesperrt, "
                "bis Zugang und Obergrenze dokumentiert freigegeben sind "
                ".")
        if geschaetzte_usd < 0:
            raise ValueError("Schaetzung darf nicht negativ sein")
        with self._sperre:
            if self.belegt_usd + geschaetzte_usd > self.obergrenze_usd:
                raise Kostengrenze(
                    f"Aufruf abgewiesen: gebucht ${self.gebucht_usd:.4f} + reserviert "
                    f"${self.reserviert_usd:.4f} + geschaetzt ${geschaetzte_usd:.4f} "
                    f"ueberschreitet die Obergrenze ${self.obergrenze_usd:.2f}.")
            marke = self._naechste_marke
            self._naechste_marke += 1
            self._reserviert[marke] = (komponente, geschaetzte_usd)
            return marke

    def gib_frei(self, marke: int) -> None:
        """Gibt eine Reservierung ohne Buchung frei (fehlgeschlagener Aufruf)."""
        with self._sperre:
            self._reserviert.pop(marke, None)

    def buche(self, marke: int, input_tokens: int, output_tokens: int,
              modellkennung: str, cache_lesen: int = 0, cache_schreiben: int = 0,
              ist_wiederholung: bool = False) -> float:
        """Bucht den tatsaechlichen Verbrauch und loest die Reservierung auf."""
        preis = self.preise.get(modellkennung)
        if preis is None:
            raise KeyError(f"kein Preis fuer Modellkennung '{modellkennung}' hinterlegt")
        betrag = preis.berechne(input_tokens, output_tokens, cache_lesen, cache_schreiben)
        with self._sperre:
            komponente, _ = self._reserviert.pop(marke, ("unbekannt", 0.0))
            v = self._verbrauch(komponente)
            v.aufrufe += 1
            v.input_tokens += input_tokens
            v.output_tokens += output_tokens
            v.cache_lesen_tokens += cache_lesen
            v.cache_schreiben_tokens += cache_schreiben
            v.usd += betrag
            if ist_wiederholung:
                v.wiederholungen += 1
        return betrag

    def buche_replay(self, komponente: str) -> None:
        """Replay einer gespeicherten Antwort: gezaehlt, aber NICHT als API-Verbrauch."""
        with self._sperre:
            self._verbrauch(komponente).replays += 1

    # ------------------------------------------------------------------
    def warnung_faellig(self) -> bool:
        if self.obergrenze_usd is None:
            return False
        if self.warnung_ausgegeben:
            return False
        if self.belegt_usd >= self.warnschwelle * self.obergrenze_usd:
            self.warnung_ausgegeben = True
            return True
        return False

    def bericht(self) -> dict[str, Any]:
        return {
            "obergrenze_usd": self.obergrenze_usd,
            "gebucht_usd": round(self.gebucht_usd, 4),
            "reserviert_usd": round(self.reserviert_usd, 4),
            "rest_usd": None if self.obergrenze_usd is None else round(self.rest_usd, 4),
            "je_komponente": {k: v.als_dict() for k, v in sorted(self.je_komponente.items())},
        }


# --------------------------------------------------------------------------- Wiederholungen

@dataclass
class Wiederholungsregel:
    """Vorab festgelegte, armneutrale Regel. Jede Wiederholung wird gekennzeichnet."""
    max_versuche: int = 3
    retry_bei: tuple[str, ...] = ("rate_limit", "serverfehler", "zeitueberschreitung",
                                  "verbindungsfehler")
    kein_retry_bei: tuple[str, ...] = ("ungueltige_anfrage", "authentifizierung",
                                       "inhaltsfilter", "kostengrenze")
    grundverzoegerung_s: float = 2.0
    faktor: float = 3.0
    protokoll: list[dict[str, Any]] = field(default_factory=list)

    def darf_wiederholen(self, fehlerart: str, versuch: int) -> bool:
        if fehlerart in self.kein_retry_bei:
            return False
        return fehlerart in self.retry_bei and versuch < self.max_versuche

    def verzoegerung_s(self, versuch: int) -> float:
        return self.grundverzoegerung_s * (self.faktor ** (versuch - 1))

    def vermerke(self, episode_id: str, versuch: int, fehlerart: str, entscheidung: str) -> None:
        self.protokoll.append({
            "episode_id": episode_id, "versuch": versuch, "fehlerart": fehlerart,
            "entscheidung": entscheidung,
        })
