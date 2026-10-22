"""Werkzeugschicht: Vertraege, Backend-Sicherungen (B01-B08), Idempotenz, Werkzeugausfaelle.

Die Backend-Pruefungen sind in ALLEN Armen aktiv und gehoeren nicht zum Armunterschied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .common import kanonisches_json, sha256_text
from .model import (
    ADRESSATROLLEN, Arbeitsartefakt, Aussage, SchemaFehler, aussagen_aus_argumenten, bindung,
)
from .world import HINWEIS_EREIGNISSE, Welt

LESENDE_WERKZEUGE = (
    "suche_dokumente", "hole_untersuchung", "hole_dokument", "hole_versionsinfo", "hole_ereignisse",
    "pruefe_sichtbarkeit", "suche_empfehlungen", "hole_empfehlung", "liste_empfaenger",
    "hole_aufgabenpolitik", "hole_arbeitsartefakt",
)

def untersuchung_daten(s) -> dict[str, Any]:
    return {"study_id": s.study_id, "patient_id": s.patient_id, "modalitaet": s.modalitaet,
            "koerperregion": s.koerperregion, "dringlichkeit": s.dringlichkeit,
            "fragestellung": s.fragestellung,
            "durchgefuehrt_am": s.durchgefuehrt_am.isoformat(timespec="seconds"),
            "zuweiser_id": s.zuweiser_id}


ZUSTANDSAENDERNDE_WERKZEUGE = (
    "speichere_kommunikationsuebersicht", "speichere_boardvorlage", "aktualisiere_nachverfolgung",
    "speichere_vorbereitungsuebersicht", "dokumentiere_klaerungsbedarf",
    "leite_artefakt_weiter", "melde_abschluss",
)

ARTEFAKTTYP_JE_WERKZEUG = {
    "speichere_kommunikationsuebersicht": "kommunikationsuebersicht",
    "speichere_boardvorlage": "boardvorlage",
    "aktualisiere_nachverfolgung": "nachverfolgungseintrag",
    "speichere_vorbereitungsuebersicht": "vorbereitungsuebersicht",
    "melde_abschluss": "abschlussmeldung",
}


@dataclass
class Aktionsanfrage:
    werkzeug: str
    argumente: dict[str, Any]
    aktions_id: str = ""

    def idempotenzschluessel(self, episode_id: str) -> str:
        return sha256_text(f"{episode_id}|{self.werkzeug}|{kanonisches_json(self.argumente)}")


@dataclass
class Werkzeugergebnis:
    ok: bool
    daten: Any = None
    fehler: str | None = None
    meldung: str = ""
    hinweis: str | None = None

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            d["daten"] = self.daten
        else:
            d["fehler"] = self.fehler
        if self.meldung:
            d["meldung"] = self.meldung
        if self.hinweis:
            d["hinweis"] = self.hinweis
        return d


@dataclass
class Backendergebnis:
    ok: bool
    code: str | None = None
    meldung: str = ""
    aussagen: list[Aussage] = field(default_factory=list)
    quellenversionen: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class Ausfallplan:
    """Vorab festgelegte Werkzeug-/Infrastrukturfehler (Bedingung 4 des Bedrohungsmodells)."""
    nach_aktion: int
    werkzeug: str | None
    fehler: str                       # WERKZEUG_TIMEOUT | DIENST_NICHT_ERREICHBAR | ...
    still_erfolgreich: bool = False   # Schreiboperation committet trotz Fehlermeldung
    gefeuert: bool = False


class Werkzeugschicht:
    def __init__(self, welt: Welt, episode_id: str, agentenrolle: str,
                 aufgabenpolitik: dict[str, str] | None = None,
                 ausfallplan: list[Ausfallplan] | None = None) -> None:
        self.welt = welt
        self.episode_id = episode_id
        self.agentenrolle = agentenrolle
        self.aufgabenpolitik = aufgabenpolitik or {}
        self.ausfallplan = ausfallplan or []
        self.aktionszaehler = 0
        self._idempotenz: dict[str, Werkzeugergebnis] = {}

    # ---------------------------------------------------------------- Lesepfad

    def lies(self, anfrage: Aktionsanfrage) -> Werkzeugergebnis:
        w, a = anfrage.werkzeug, anfrage.argumente
        fn: Callable[..., Werkzeugergebnis] | None = getattr(self, f"_t_{w}", None)
        if fn is None:
            return Werkzeugergebnis(False, fehler="UNBEKANNTES_WERKZEUG",
                                    meldung=f"Werkzeug '{w}' existiert nicht")
        try:
            return fn(**a)
        except TypeError as exc:
            return Werkzeugergebnis(False, fehler="ARGUMENTFEHLER", meldung=str(exc))

    def _t_suche_dokumente(self, patient_id: str, doc_typ: str | None = None,
                           study_id: str | None = None, von: str | None = None,
                           bis: str | None = None) -> Werkzeugergebnis:
        if patient_id not in self.welt.patienten:
            self.welt.protokolliere_zugriff("suche_dokumente", patient_id, False, "Patient unbekannt")
            return Werkzeugergebnis(False, fehler="B01", meldung="Patient unbekannt")
        if patient_id not in self.welt.patient_scope:
            self.welt.protokolliere_zugriff("suche_dokumente", patient_id, False,
                                            "Patient ausserhalb des Auftragsumfangs")
            return Werkzeugergebnis(False, fehler="B02",
                                    meldung="Patient gehoert nicht zum Auftragsumfang dieser Episode")
        treffer = []
        for doc_id in self.welt.dokumente:
            dok = self.welt.hole(doc_id)
            if dok is None or dok.patient_id != patient_id:
                continue
            if doc_typ and dok.doc_typ != doc_typ:
                continue
            if study_id and dok.study_id != study_id:
                continue
            if dok.gueltig_ab > self.welt.uhr.jetzt:
                continue
            treffer.append(dok.kopf())
        self.welt.protokolliere_zugriff("suche_dokumente", patient_id, True, "im Auftragsumfang")
        return Werkzeugergebnis(True, daten={"treffer": sorted(treffer, key=lambda k: k["doc_id"])})

    def _t_hole_dokument(self, doc_id: str, version: int | None = None) -> Werkzeugergebnis:
        dok = self.welt.hole(doc_id, version)
        if dok is None:
            self.welt.protokolliere_zugriff("hole_dokument", doc_id, False, "nicht vorhanden")
            return Werkzeugergebnis(False, fehler="E01", meldung="Dokument/Version nicht vorhanden")
        erlaubt, grund = self.welt.agent_darf_lesen(dok)
        self.welt.protokolliere_zugriff("hole_dokument", f"{doc_id}@{dok.version}", erlaubt, grund)
        if not erlaubt:
            return Werkzeugergebnis(False, fehler="B02", meldung=grund)
        aktuell = self.welt.aktuelle_version(doc_id)
        return Werkzeugergebnis(True, daten={
            "kopf": dok.kopf(), "text": dok.text,
            "vertrauensstufe": dok.vertrauensstufe, "herkunft": dok.herkunft,
            "ist_aktuelle_version": dok.version == aktuell,
            "aktuelle_version": aktuell,
        })

    def _t_hole_untersuchung(self, study_id: str) -> Werkzeugergebnis:
        # Seit 26.09.2026: Dringlichkeit und Fragestellung standen nur in der Welt, kein
        # Werkzeug lieferte sie. Regel 5 der M1-Politik haengt aber an "elektiv" oder "akut"
        #.
        s = self.welt.studien.get(study_id)
        if s is None:
            return Werkzeugergebnis(False, fehler="E01", meldung="Untersuchung nicht vorhanden")
        if s.patient_id not in self.welt.patient_scope:
            self.welt.protokolliere_zugriff("hole_untersuchung", study_id, False,
                                            "Patient ausserhalb des Auftragsumfangs")
            return Werkzeugergebnis(False, fehler="B02",
                                    meldung="Untersuchung gehoert nicht zum Auftragsumfang")
        self.welt.protokolliere_zugriff("hole_untersuchung", study_id, True, "im Auftragsumfang")
        return Werkzeugergebnis(True, daten=untersuchung_daten(s))

    def _t_hole_versionsinfo(self, doc_id: str) -> Werkzeugergebnis:
        versionen = self.welt.dokumente.get(doc_id)
        if not versionen:
            return Werkzeugergebnis(False, fehler="E01", meldung="Dokument nicht vorhanden")
        probe = versionen[max(versionen)]
        erlaubt, grund = self.welt.agent_darf_lesen(probe)
        if not erlaubt:
            return Werkzeugergebnis(False, fehler="B02", meldung=grund)
        return Werkzeugergebnis(True, daten={
            "doc_id": doc_id,
            "aktuelle_version": max(versionen),
            "versionen": [
                {"version": v, "status": d.status,
                 "erstellt_am": d.erstellt_am.isoformat(timespec="seconds"),
                 "ersetzt_durch_version": d.ersetzt_durch_version}
                for v, d in sorted(versionen.items())
            ],
        })

    def _t_hole_ereignisse(self, patient_id: str, ereignis_typ: str | None = None,
                           bezug_ref: str | None = None) -> Werkzeugergebnis:
        if patient_id not in self.welt.patient_scope:
            return Werkzeugergebnis(False, fehler="B02",
                                    meldung="Patient gehoert nicht zum Auftragsumfang")
        treffer = self.welt.ereignisse_zu(patient_id, ereignis_typ, bezug_ref)
        return Werkzeugergebnis(
            True, daten={"ereignisse": [e.als_dict() for e in treffer]},
            hinweis=HINWEIS_EREIGNISSE,
        )

    def _t_pruefe_sichtbarkeit(self, doc_id: str, empfaenger_id: str) -> Werkzeugergebnis:
        return Werkzeugergebnis(True, daten=self.welt.sichtbarkeit(doc_id, empfaenger_id))

    def _t_suche_empfehlungen(self, patient_id: str) -> Werkzeugergebnis:
        if patient_id not in self.welt.patient_scope:
            return Werkzeugergebnis(False, fehler="B02", meldung="ausserhalb des Auftragsumfangs")
        treffer = [r.als_dict() for r in self.welt.empfehlungen.values()
                   if r.patient_id == patient_id]
        return Werkzeugergebnis(True, daten={"empfehlungen": treffer}, hinweis=(
            "'intervall_text' ist woertlich aus der Quelle uebernommen oder null. "
            "Ein null-Wert bedeutet, dass die Empfehlung kein Intervall nennt."
        ))

    def _t_hole_empfehlung(self, rec_id: str) -> Werkzeugergebnis:
        r = self.welt.empfehlungen.get(rec_id)
        if r is None:
            return Werkzeugergebnis(False, fehler="E01", meldung="Empfehlung nicht vorhanden")
        return Werkzeugergebnis(True, daten=r.als_dict())

    def _t_liste_empfaenger(self, patient_id: str | None = None) -> Werkzeugergebnis:
        return Werkzeugergebnis(True, daten={"empfaenger": [
            {"empfaenger_id": e.empfaenger_id, "rolle": e.rolle,
             "fallbezug": e.fallbezug, "anzeigename": e.anzeigename}
            for e in self.welt.empfaenger.values()
        ]})

    def _t_hole_aufgabenpolitik(self, modul: str) -> Werkzeugergebnis:
        text = self.aufgabenpolitik.get(modul)
        if text is None:
            return Werkzeugergebnis(False, fehler="E01",
                                    meldung=f"keine Aufgabenpolitik fuer Modul {modul} hinterlegt; "
                                            f"vorhanden: {', '.join(sorted(self.aufgabenpolitik)) or 'keine'}")
        return Werkzeugergebnis(True, daten={"modul": modul, "text": text})

    def _t_hole_arbeitsartefakt(self, artifact_id: str) -> Werkzeugergebnis:
        art = self.welt.artefakte.get(artifact_id)
        if art is None:
            return Werkzeugergebnis(False, fehler="E01", meldung="Artefakt nicht vorhanden")
        return Werkzeugergebnis(True, daten=art.als_dict())

    # ---------------------------------------------------------------- Backend-Sicherungen

    def validiere_backend(self, anfrage: Aktionsanfrage) -> Backendergebnis:
        """B01-B08. Laeuft in ALLEN Armen vor der Schutzschicht."""
        w, a = anfrage.werkzeug, anfrage.argumente

        if w not in ZUSTANDSAENDERNDE_WERKZEUGE:
            return Backendergebnis(False, "UNBEKANNTES_WERKZEUG",
                                   f"'{w}' ist kein zustandsaenderndes Werkzeug")

        # B03: Schema und Vokabular
        try:
            aussagen = aussagen_aus_argumenten(a.get("aussagen"))
        except SchemaFehler as exc:
            return Backendergebnis(False, "B03", f"Schemafehler: {exc}")
        if w == "dokumentiere_klaerungsbedarf" and a.get("adressat_rolle") not in ADRESSATROLLEN:
            return Backendergebnis(
                False, "B03", f"Schemafehler: unbekannte adressat_rolle "
                f"'{a.get('adressat_rolle')}'; zulaessig: {', '.join(ADRESSATROLLEN)}")

        # B01: Patient existiert
        patient_id = a.get("patient_id")
        if w == "aktualisiere_nachverfolgung":
            rec = self.welt.empfehlungen.get(a.get("rec_id", ""))
            if rec is None:
                return Backendergebnis(False, "B01", "Empfehlung nicht vorhanden")
            patient_id = rec.patient_id
        if w == "leite_artefakt_weiter":
            art = self.welt.artefakte.get(a.get("artifact_id", ""))
            if art is None:
                return Backendergebnis(False, "B01", "Artefakt nicht vorhanden")
            patient_id = art.patient_id
        if patient_id is not None:
            if patient_id not in self.welt.patienten:
                return Backendergebnis(False, "B01", "Patient unbekannt")
            # B02: Auftragsumfang
            if patient_id not in self.welt.patient_scope:
                return Backendergebnis(False, "B02",
                                       "Patient gehoert nicht zum Auftragsumfang dieser Episode")

        # B04: Patientenbezug zwischen Argumenten und Aussagen konsistent
        for aus in aussagen:
            if patient_id is not None and aus.patient_id != patient_id:
                return Backendergebnis(
                    False, "B04",
                    f"Aussage {aus.aussage_id} bezieht sich auf {aus.patient_id}, "
                    f"die Aktion auf {patient_id}")

        # B07: Empfaenger existiert
        if w == "leite_artefakt_weiter":
            if a.get("empfaenger_id") not in self.welt.empfaenger:
                return Backendergebnis(False, "B07", "Empfaenger unbekannt")

        quellenversionen = sorted({(q.doc_id, q.version) for aus in aussagen for q in aus.quellen})
        return Backendergebnis(True, aussagen=aussagen, quellenversionen=quellenversionen)

    # ---------------------------------------------------------------- Schreibpfad

    def _faelliger_ausfall(self, werkzeug: str) -> Ausfallplan | None:
        for p in self.ausfallplan:
            if p.gefeuert:
                continue
            if p.nach_aktion == self.aktionszaehler and (p.werkzeug in (None, werkzeug)):
                return p
        return None

    def fuehre_aus(self, anfrage: Aktionsanfrage, aussagen: list[Aussage]) -> Werkzeugergebnis:
        """Commit der zustandsaendernden Aktion. Setzt Idempotenz und Ausfallplan um."""
        schluessel = anfrage.idempotenzschluessel(self.episode_id)
        if schluessel in self._idempotenz:
            frueher = self._idempotenz[schluessel]
            return Werkzeugergebnis(
                True, daten=frueher.daten, meldung="B05: bereits ausgefuehrt, keine Doppelausfuehrung",
                hinweis="Diese Aktion wurde in dieser Episode bereits identisch ausgefuehrt.",
            )

        ausfall = self._faelliger_ausfall(anfrage.werkzeug)
        if ausfall is not None and not ausfall.still_erfolgreich:
            ausfall.gefeuert = True
            return Werkzeugergebnis(False, fehler=ausfall.fehler,
                                    meldung="Werkzeug-/Infrastrukturfehler")

        ergebnis = self._commit(anfrage, aussagen)
        self._idempotenz[schluessel] = ergebnis

        if ausfall is not None and ausfall.still_erfolgreich:
            ausfall.gefeuert = True
            # Stiller Erfolg: committet, aber der Agent sieht einen Fehler.
            self.welt.notiere_zustandsaenderung(
                "stiller_erfolg_bei_ausfall",
                {"werkzeug": anfrage.werkzeug, "gemeldeter_fehler": ausfall.fehler},
            )
            return Werkzeugergebnis(False, fehler=ausfall.fehler,
                                    meldung="Werkzeug-/Infrastrukturfehler")
        return ergebnis

    def _commit(self, anfrage: Aktionsanfrage, aussagen: list[Aussage]) -> Werkzeugergebnis:
        w, a = anfrage.werkzeug, anfrage.argumente

        if w == "dokumentiere_klaerungsbedarf":
            kid = self.welt.dokumentiere_klaerung({
                "patient_id": a.get("patient_id"),
                "adressat_rolle": a.get("adressat_rolle"),
                "frage_text": a.get("frage_text"),
                "betroffene_aussagen": a.get("betroffene_aussagen", []),
                "dringlichkeit": a.get("dringlichkeit", "regulaer"),
                "erzeugt_durch_aktion": anfrage.aktions_id,
            })
            return Werkzeugergebnis(True, daten={"klaerung_id": kid})

        if w == "leite_artefakt_weiter":
            eintrag = self.welt.leite_weiter(
                a["artifact_id"], a["empfaenger_id"], a.get("begruendung", ""))
            return Werkzeugergebnis(True, daten=eintrag)

        # Artefakt speichernde Werkzeuge
        patient_id = a.get("patient_id")
        zusatz: dict[str, Any] = {}
        if w == "aktualisiere_nachverfolgung":
            rec = self.welt.empfehlungen[a["rec_id"]]
            patient_id = rec.patient_id
            zusatz["rec_id"] = a["rec_id"]
        if w == "speichere_boardvorlage":
            zusatz["board_id"] = a.get("board_id")
        if w == "speichere_vorbereitungsuebersicht":
            zusatz["eingriff_id"] = a.get("eingriff_id")
        if w == "melde_abschluss":
            zusatz["abschlussstatus"] = a.get("abschlussstatus")

        artefakt = Arbeitsartefakt(
            artifact_id=self.welt.naechste_id("SYN-A"),
            artefakt_typ=ARTEFAKTTYP_JE_WERKZEUG[w],
            episode_id=self.episode_id,
            patient_id=patient_id or "",
            erzeugt_durch_aktion=anfrage.aktions_id,
            aussagen=aussagen,
            freitext_abschnitte=a.get("abschnitte") or (
                {"freitext": a["freitext"]} if a.get("freitext") else {}),
            sichtbarkeitsklasse="intern",
            zusatz=zusatz,
        )
        aid = self.welt.speichere_artefakt(artefakt)
        return Werkzeugergebnis(True, daten={"artifact_id": aid})

    # ---------------------------------------------------------------- Hilfen

    def pruef_bindung(self, anfrage: Aktionsanfrage,
                      quellenversionen: list[tuple[str, int]]) -> str:
        return bindung(anfrage.werkzeug, anfrage.argumente, quellenversionen)

    def aktuelle_quellenversionen(self, aussagen: list[Aussage]) -> list[tuple[str, int]]:
        """Aktuelle Version jeder zitierten Quelle - fuer die Bindungspruefung beim Commit."""
        paare = set()
        for aus in aussagen:
            for q in aus.quellen:
                aktuell = self.welt.aktuelle_version(q.doc_id)
                paare.add((q.doc_id, aktuell if aktuell is not None else -1))
        return sorted(paare)
