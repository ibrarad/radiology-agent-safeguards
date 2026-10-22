"""K2 - regelbasierte Referenzloesung ohne LLM.

GELTUNGSBEREICH, VORAB FESTGELEGT UND BEWUSST ENG:
K2 bearbeitet ausschliesslich die vollstaendig strukturierten Teilaufgaben, die sich ohne
jedes Textverstaendnis aus autoritativen Metadaten und dokumentierten Ereignissen ergeben:

    (a) Befundstatus       - aus dem Dokumentstatus der aktuellen Version
    (b) Sichtbarkeitsstatus - aus der Sichtbarkeitsfunktion
    (c) Kommunikationsstatus - aus dem Vorhandensein eines Gespraechsvermerks zum Befund
    (d) Nachverfolgungsstatus - aus der dokumentierten Ereignislage, nur bei Eindeutigkeit

K2 kann NICHT: Gewissheit, Negation oder Zeitbezug eines Befundes beurteilen, Widersprueche
aufloesen, relevante Auslassungen erkennen oder Klaerungsbedarf inhaltlich formulieren.
Fuer den Befundgegenstand selbst gibt K2 deshalb ausdruecklich 'unbestimmt/unklar' an
(Aussagestaerke 0) und meldet die Aufgabe als nur teilweise bearbeitet.

Diese eingeschraenkte Aufgabenabdeckung ist das Ergebnis und wird berichtet. K2 nutzt
    - KEINE Goldlabels,
    - KEINE speziell fuer Haupttestfaelle geschriebenen Regeln,
    - nur die oeffentliche Begriffssystematik aus ragis.begriffe.
"""
from __future__ import annotations

from typing import Any

from .begriffe import erkannte_codes
from .tools import Aktionsanfrage

# Ereignistyp -> Nachverfolgungsstatus, nur wo die Zuordnung eindeutig ist.
EREIGNIS_ZU_NACHVERFOLGUNG = [
    ("fragestellung_beurteilt", "fragestellung_beurteilt"),
    ("untersuchung_durchgefuehrt", "untersuchung_durchgefuehrt"),
    ("termin_vereinbart", "termin_vereinbart"),
    ("weiterverfolgung_veranlasst", "weiterverfolgung_veranlasst"),
    ("empfehlung_dokumentiert", "empfehlung_dokumentiert"),
]


class RegelbasierterAgent:
    """Deterministischer Agent ohne Modellaufruf. Kontrolle K2, kein Hauptarm."""

    ist_platzhalter = False          # kein Platzhalter, sondern eine echte Vergleichsloesung
    nutzt_modell = False

    def __init__(self, patient_id: str, study_id: str | None = None,
                 rec_id: str | None = None, empfaenger_id: str = "SYN-X0002",
                 kennung: str = "k2-regelbasiert-v0.1") -> None:
        self.kennung = kennung
        self.patient_id = patient_id
        self.study_id = study_id
        self.rec_id = rec_id
        self.empfaenger_id = empfaenger_id
        self._schritt = 0
        self._dokumente: list[dict[str, Any]] = []
        self._texte: dict[str, str] = {}
        self._ereignisse: list[dict[str, Any]] = []
        self._sichtbarkeit: dict[str, str] = {}
        self._zieldoc: str | None = None
        self._abdeckung: dict[str, Any] = {
            "bearbeitete_teilaufgaben": [], "nicht_bearbeitbar": [],
        }

    # ------------------------------------------------------------------
    @property
    def abdeckungsbericht(self) -> dict[str, Any]:
        return self._abdeckung

    def naechste_aktion(self, beobachtung: dict[str, Any] | None) -> Aktionsanfrage | None:
        if beobachtung is not None:
            self._verarbeite(beobachtung)
        self._schritt += 1

        if self._schritt == 1:
            return Aktionsanfrage("suche_dokumente", {"patient_id": self.patient_id})
        if self._schritt == 2:
            return Aktionsanfrage("hole_ereignisse", {"patient_id": self.patient_id})

        # Befunddokumente der Reihe nach holen
        offene = [d for d in self._dokumente
                  if d["doc_typ"] in ("befund", "nachtrag") and d["doc_id"] not in self._texte
                  and (self.study_id is None or d.get("study_id") == self.study_id)]
        if offene:
            return Aktionsanfrage("hole_dokument", {"doc_id": offene[0]["doc_id"]})

        if self._zieldoc is None:
            self._zieldoc = self._waehle_zieldokument()
        if self._zieldoc and self._zieldoc not in self._sichtbarkeit:
            return Aktionsanfrage("pruefe_sichtbarkeit",
                                  {"doc_id": self._zieldoc, "empfaenger_id": self.empfaenger_id})

        if not any(s.startswith("speichern") for s in self._abdeckung["bearbeitete_teilaufgaben"]):
            return self._speichere()

        if "abschluss" not in self._abdeckung["bearbeitete_teilaufgaben"]:
            self._abdeckung["bearbeitete_teilaufgaben"].append("abschluss")
            return Aktionsanfrage("melde_abschluss", {
                "patient_id": self.patient_id,
                "abschlussstatus": "teilweise_bearbeitet_klaerung_hinterlegt",
                "freitext": ("Regelbasierte Bearbeitung: Status aus autoritativen Metadaten "
                             "und dokumentierten Ereignissen uebernommen. Eine inhaltliche "
                             "Beurteilung des Befundes ist ohne Textverstaendnis nicht "
                             "moeglich und wurde nicht vorgenommen."),
                "aussagen": []})
        return None

    # ------------------------------------------------------------------
    def _verarbeite(self, beobachtung: dict[str, Any]) -> None:
        erg = beobachtung.get("ergebnis") or {}
        if not erg.get("ok"):
            return
        daten = erg.get("daten") or {}
        if "treffer" in daten:
            self._dokumente = daten["treffer"]
        elif "ereignisse" in daten:
            self._ereignisse = daten["ereignisse"]
        elif "kopf" in daten:
            self._texte[daten["kopf"]["doc_id"]] = daten.get("text", "")
        elif "status" in daten and "begruendung" in daten:
            if self._zieldoc:
                self._sichtbarkeit[self._zieldoc] = daten["status"]

    def _waehle_zieldokument(self) -> str | None:
        kandidaten = [d for d in self._dokumente
                      if d["doc_typ"] in ("befund", "nachtrag")
                      and (self.study_id is None or d.get("study_id") == self.study_id)]
        if not kandidaten:
            self._abdeckung["nicht_bearbeitbar"].append("kein Befunddokument auffindbar")
            return None
        # Eindeutigkeitsregel: genau ein Befund je Untersuchung, sonst Abbruch der Teilaufgabe.
        befunde = [d for d in kandidaten if d["doc_typ"] == "befund"]
        if len(befunde) != 1:
            self._abdeckung["nicht_bearbeitbar"].append(
                f"{len(befunde)} Befunddokumente - keine eindeutige Zuordnung ohne Textanalyse")
            return None
        return befunde[0]["doc_id"]

    # ------------------------------------------------------------------
    def _speichere(self) -> Aktionsanfrage | None:
        self._abdeckung["bearbeitete_teilaufgaben"].append("speichern")
        if self._zieldoc is None:
            self._abdeckung["nicht_bearbeitbar"].append("keine Aussage erzeugbar")
            return Aktionsanfrage("melde_abschluss", {
                "patient_id": self.patient_id, "abschlussstatus": "nicht_bearbeitbar",
                "freitext": "Kein eindeutiges Befunddokument.", "aussagen": []})

        kopf = next(d for d in self._dokumente if d["doc_id"] == self._zieldoc)
        text = self._texte.get(self._zieldoc, "")
        codes = erkannte_codes(text)
        if len(codes) != 1:
            self._abdeckung["nicht_bearbeitbar"].append(
                f"{len(codes)} Befundcodes lexikalisch erkannt - ohne Bedeutungsanalyse "
                f"nicht entscheidbar")
            return Aktionsanfrage("melde_abschluss", {
                "patient_id": self.patient_id, "abschlussstatus": "nicht_bearbeitbar",
                "freitext": "Befundgegenstand nicht eindeutig lexikalisch bestimmbar.",
                "aussagen": []})
        code = codes[0]
        quelle = [{"doc_id": self._zieldoc, "version": kopf["version"], "belegstelle": ""}]

        def basis(aid: str, art: str, status: tuple[str, str]) -> dict[str, Any]:
            return {
                "aussage_id": aid, "art": art,
                "gegenstand": {"befund_code": code, "koerperregion": "",
                               "lateralitaet": "nicht_zutreffend", "laesion_ref": None},
                "zuordnung": {"patient_id": self.patient_id, "study_id": self.study_id},
                # Ausdrueckliche Enthaltung zur Gewissheit: K2 beurteilt Inhalte nicht.
                "zeitbezug": {"bezugszeitpunkt": None,
                              "zeitliche_qualifikation": "zeitlich_unbekannt"},
                "polaritaet": "unbestimmt", "gewissheit": "unklar",
                "quellen": quelle,
                "behaupteter_status": {"status_typ": status[0], "status_wert": status[1]},
                "historisch_markiert": False,
            }

        aussagen = [basis("k2a", "status_aussage", ("befundstatus", kopf["status"]))]
        self._abdeckung["bearbeitete_teilaufgaben"].append("befundstatus")

        sicht = self._sichtbarkeit.get(self._zieldoc)
        if sicht:
            aussagen.append(basis("k2b", "status_aussage", ("sichtbarkeitsstatus", sicht)))
            self._abdeckung["bearbeitete_teilaufgaben"].append("sichtbarkeitsstatus")

        kommuniziert = any(
            e["ereignis_typ"] == "persoenliche_kommunikation_dokumentiert"
            and e["bezug_ref"] == self._zieldoc for e in self._ereignisse)
        aussagen.append(basis(
            "k2c", "prozess_aussage",
            ("kommunikationsstatus",
             "persoenlich_kommuniziert_dokumentiert" if kommuniziert
             else "kommunikation_nicht_dokumentiert")))
        self._abdeckung["bearbeitete_teilaufgaben"].append("kommunikationsstatus")
        self._abdeckung["nicht_bearbeitbar"].extend([
            "Gewissheit und Negation des Befundes",
            "Zeitbezug des Befundes",
            "Aufloesung von Widerspruechen",
            "Erkennen relevanter Auslassungen",
        ])

        return Aktionsanfrage("speichere_kommunikationsuebersicht", {
            "patient_id": self.patient_id, "study_id": self.study_id, "aussagen": aussagen})
