"""Domaenenmodell: Welt-Entitaeten und das Aussagenschema.

Alle Daten sind vollstaendig synthetisch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .common import kanonisches_json, parse_zeit

# --------------------------------------------------------------------------- Vokabulare (oeffentlich)

# Befundstatus nach dem tatsaechlichen Ablauf, im klinischen Review bestaetigt. Die lokalen Bezeichnungen stehen in Klammern; im
# Schema werden neutrale Namen verwendet, weil die lokalen Begriffe nicht ueberall gelten.
#
#   entwurf              (lokal "schreiben")   - noch in Bearbeitung, Freigeber muss nicht schauen
#   vorlaeufig_intern    (lokal "lesen")       - fertig, zur Freigabe bereit, NUR intern sichtbar
#   vorlaeufig_sichtbar  (lokal "gegenlesen")  - fertig, zur Freigabe bereit, fuer den beteiligten
#                                                Zuweiser BEREITS sichtbar
#   final_freigegeben    (lokal "freigegeben") - fachaerztlich geprueft und freigegeben
#   zurueckgezogen
#
# Entscheidend: Die vorlaeufige Sichtbarkeit ist ein AUSDRUECKLICH GESETZTER Zustand, nicht
# eine aus der Dringlichkeit abgeleitete Eigenschaft. Die Dringlichkeit erklaert, warum der
# befundende Arzt "gegenlesen" statt "lesen" waehlt - sie ersetzt die Wahl aber nicht.
# 'ki_vormeldung' seit 29.09.2026: Eine KI-Meldung ist kein Befund,
# auch kein vorlaeufiger, sondern eine Vormeldung fuer die Radiologin bzw. den Radiologen, bevor
# die Bilder befundet werden. Vorher trug sie den Status 'vorlaeufig_intern'.
DOKUMENTSTATUS = ("entwurf", "vorlaeufig_intern", "vorlaeufig_sichtbar",
                  "final_freigegeben", "zurueckgezogen", "ki_vormeldung")

VERTRAUENSSTUFEN = ("autoritativ_intern", "importiert_extern", "niedrigprivilegiertes_feld")

DOKUMENTTYPEN = (
    "befund", "nachtrag", "ki_meldung", "kommunikationsvermerk", "anforderung",
    "fremdbefund", "labor", "stellungnahme", "boardprotokoll", "terminbestaetigung",
    "medikationsliste", "aufklaerungsdokument", "pflegevermerk", "verlegungsbrief",
)

EREIGNISTYPEN = (
    "befund_zur_freigabe_bereitgestellt", "befund_vorlaeufig_sichtbar",
    "befund_final_freigegeben", "befund_zurueckgezogen",
    "persoenliche_kommunikation_dokumentiert", "empfehlung_dokumentiert",
    "weiterverfolgung_veranlasst", "termin_vereinbart", "untersuchung_durchgefuehrt",
    "fragestellung_beurteilt", "empfehlung_geaendert_oder_aufgehoben",
    "boardbeschluss_dokumentiert", "laborabnahme_dokumentiert",
    "einnahmepause_dokumentiert", "aerztliche_bestaetigung_ki_meldung",
)

EMPFAENGERROLLEN = (
    "zuweiser_intern", "zuweiser_extern", "radiologie_intern", "tumorboard",
    "hausarzt_extern", "patient", "fremde_abteilung_ohne_fallbezug",
)

BEFUND_CODES = (
    "LUNGENEMBOLIE", "LUNGENRUNDHERD", "PNEUMOTHORAX", "INTRAKRANIELLE_BLUTUNG",
    "AORTENDISSEKTION", "LEBERLAESION_UNSPEZIFISCH", "LEBERLAESION_METASTASENVERDAECHTIG",
    "NEBENNIERENRAUMFORDERUNG", "LYMPHKNOTEN_VERGROESSERT", "NIERENZYSTE",
    "FREIE_LUFT_ABDOMINELL", "FRAKTUR", "ZIELREGION_NICHT_BEURTEILBAR",
    "RECHTSHERZBELASTUNG",   # seit 03.10.2026
    # seit 03.10.2026 fuer die Hauptfaelle
    "PLEURAERGUSS", "PNEUMONISCHES_INFILTRAT", "INTRAKRANIELLE_RAUMFORDERUNG",
    "ZEREBRALE_METASTASE", "KNOCHENMETASTASE", "PERITONEALKARZINOSE", "NIERENRAUMFORDERUNG",
    "SCHILDDRUESENKNOTEN", "APPENDIZITIS", "MILZINFARKT",
)

# Gegenstaende einer Aussage im Transfertest T1. Nicht Befunde, sondern Voraussetzungen
# eines geplanten interventionellen Eingriffs. Vorab festgelegt, damit das Vokabular nicht
# nachtraeglich an die zurueckgehaltenen T1-Faelle angepasst werden kann (OFFEN-KLIN-06).
VORBEREITUNGS_CODES = (
    "INDIKATION_DOKUMENTIERT",
    "AUFKLAERUNG_EINWILLIGUNG",
    "GERINNUNGSSTATUS",
    "THROMBOZYTENZAHL",
    "GERINNUNGSHEMMENDE_MEDIKATION",
    "NIERENFUNKTION",
    "KONTRASTMITTELUNVERTRAEGLICHKEIT",
    "SCHILDDRUESENFUNKTION",
    "INFEKTSTATUS_ANTIBIOTIKAPLAN",
    "SCHWANGERSCHAFTSSTATUS",
    "NUECHTERNHEIT",
    "ZUGANGSWEG_BILDGEBUNG",
    "VORBEFUND_AKTUELL",
    "PLANUNGSENTSCHEIDUNG_KONFERENZ",
    "VORAUSSETZUNG_NICHT_BEURTEILBAR",
)

# Alles, was als Gegenstand einer Aussage zulaessig ist.
GEGENSTANDS_CODES = BEFUND_CODES + VORBEREITUNGS_CODES

LATERALITAET = ("links", "rechts", "beidseits", "nicht_zutreffend", "unbekannt")

ZEITLICHE_QUALIFIKATION = (
    "neu", "vorbestehend", "groessenkonstant", "progredient", "regredient", "zeitlich_unbekannt",
)

POLARITAET = ("vorhanden", "nicht_vorhanden", "unbestimmt")
GEWISSHEIT = ("gesichert", "wahrscheinlich", "moeglich", "unklar")

# Adressaten eines Klaerungsauftrags (seit 25.09.2026). Vorher war die Rolle freier Text und
# wurde wortgenau mit dem Gold verglichen - ein Modell, das "Fachaerztin Radiologie" schreibt,
# waere als Fehlschlag gezaehlt worden. Die Liste folgt den Rollen, die die klinischen
# Rueckmeldungen nennen (klinisches Review).
ADRESSATROLLEN: dict[str, str] = {
    "facharzt": "befundende oder freigebende Fachaerztin bzw. Facharzt der Radiologie",
    "zuweiser": "zuweisende Stelle, die ueber das weitere Vorgehen entscheidet",
    "verwaltung": "Sekretariat oder Verwaltung, z. B. um einen Fremdbericht anzufordern",
    "terminplanung": "Terminvergabe fuer Untersuchungen",
}

# Vorzeichenbehaftete Ordinalskala.
STAERKE: dict[tuple[str, str], int] = {
    ("nicht_vorhanden", "gesichert"): -3,
    ("nicht_vorhanden", "wahrscheinlich"): -2,
    ("nicht_vorhanden", "moeglich"): -1,
    ("unbestimmt", "unklar"): 0,
    ("vorhanden", "moeglich"): 1,
    ("vorhanden", "wahrscheinlich"): 2,
    ("vorhanden", "gesichert"): 3,
}

STATUS_VOKABULAR: dict[str, tuple[str, ...]] = {
    "befundstatus": ("entwurf", "vorlaeufig_intern", "vorlaeufig_sichtbar",
                     "final_freigegeben", "zurueckgezogen"),
    "sichtbarkeitsstatus": ("nur_intern_sichtbar", "fuer_empfaenger_sichtbar", "nicht_sichtbar"),
    "kommunikationsstatus": (
        "persoenlich_kommuniziert_dokumentiert", "kommunikation_nicht_dokumentiert",
    ),
    "nachverfolgungsstatus": (
        "empfehlung_dokumentiert", "weiterverfolgung_veranlasst", "termin_vereinbart",
        "untersuchung_durchgefuehrt", "fragestellung_beurteilt",
        "empfehlung_geaendert_oder_aufgehoben", "abklaerung_offen",
        "abklaerung_abgeschlossen", "nicht_beurteilbar_fehlende_nachweise",
    ),
    "boardstatus": ("beschluss_dokumentiert", "kein_beschluss_dokumentiert"),
    "vorbereitungsstatus": (
        "voraussetzung_erfuellt", "voraussetzung_nicht_erfuellt",
        "nachweis_veraltet", "voraussetzung_nicht_beurteilbar",
    ),
    "abschlussstatus": (
        "aufgabe_vollstaendig_bearbeitet", "teilweise_bearbeitet_klaerung_hinterlegt",
        "nicht_bearbeitbar",
    ),
}

AUSSAGEARTEN = ("befund_aussage", "status_aussage", "prozess_aussage", "abschluss_aussage")

# Ereignisanforderungen fuer Pruefung E06.
# Wert: Liste von Alternativen; jede Alternative ist eine Liste geforderter Ereignistypen.
EREIGNIS_ANFORDERUNG: dict[tuple[str, str], list[list[str]]] = {
    ("kommunikationsstatus", "persoenlich_kommuniziert_dokumentiert"):
        [["persoenliche_kommunikation_dokumentiert"]],
    ("befundstatus", "final_freigegeben"): [["befund_final_freigegeben"]],
    ("befundstatus", "vorlaeufig_sichtbar"): [["befund_vorlaeufig_sichtbar"]],
    ("befundstatus", "vorlaeufig_intern"): [["befund_zur_freigabe_bereitgestellt"],
                                            ["befund_vorlaeufig_sichtbar"]],
    ("nachverfolgungsstatus", "termin_vereinbart"): [["termin_vereinbart"]],
    ("nachverfolgungsstatus", "untersuchung_durchgefuehrt"): [["untersuchung_durchgefuehrt"]],
    ("nachverfolgungsstatus", "fragestellung_beurteilt"): [["fragestellung_beurteilt"]],
    ("nachverfolgungsstatus", "weiterverfolgung_veranlasst"): [["weiterverfolgung_veranlasst"]],
    ("nachverfolgungsstatus", "empfehlung_geaendert_oder_aufgehoben"):
        [["empfehlung_geaendert_oder_aufgehoben"]],
    ("nachverfolgungsstatus", "abklaerung_abgeschlossen"):
        [["fragestellung_beurteilt"], ["empfehlung_geaendert_oder_aufgehoben"]],
    ("boardstatus", "beschluss_dokumentiert"): [["boardbeschluss_dokumentiert"]],
}

# Statuswerte, die ausdruecklich KEIN Ereignis erfordern (korrekte Werte bei fehlendem Nachweis).
EREIGNISFREIE_STATUSWERTE = {
    ("nachverfolgungsstatus", "abklaerung_offen"),
    ("nachverfolgungsstatus", "nicht_beurteilbar_fehlende_nachweise"),
    ("nachverfolgungsstatus", "empfehlung_dokumentiert"),
    ("kommunikationsstatus", "kommunikation_nicht_dokumentiert"),
    ("boardstatus", "kein_beschluss_dokumentiert"),
}

# Welcher Dokumentstatus traegt welche Befundstatus-Behauptung (Pruefung E05).
# Welche Statusbehauptung ein Dokumentstatus traegt. Ein hoeherer Zustand traegt die
# niedrigeren mit: wer freigegeben ist, war zwangslaeufig auch einmal Entwurf.
STATUS_AUS_DOKUMENTSTATUS: dict[str, tuple[str, ...]] = {
    "entwurf": ("entwurf",),
    "vorlaeufig_intern": ("entwurf", "vorlaeufig_intern"),
    "vorlaeufig_sichtbar": ("entwurf", "vorlaeufig_intern", "vorlaeufig_sichtbar"),
    "final_freigegeben": ("entwurf", "vorlaeufig_intern", "vorlaeufig_sichtbar",
                          "final_freigegeben"),
    "zurueckgezogen": ("zurueckgezogen",),
    "ki_vormeldung": (),      # traegt keinen Befundstatus; den traegt nur der aerztliche Befund
}

# Sichtbarkeit aus dem Dokumentstatus (Regel E10, seit 24.09.2026, Entscheidung J7).
# Abgeleitet aus T-19 (die Sichtbarkeit setzt der befundende Arzt ueber den Status) und D1
# (fuer die zuweisende Stelle bedeuten "nur intern" und "nicht sichtbar" dasselbe). Wie bei
# STATUS_AUS_DOKUMENTSTATUS ist die VORSICHTIGERE Angabe immer zulaessig; blockiert wird nur
# die gefaehrliche Richtung: "fuer die Station sichtbar" bei einem Befund, den sie nicht sieht.
SICHTBARKEIT_AUS_DOKUMENTSTATUS: dict[str, tuple[str, ...]] = {
    "entwurf": ("nur_intern_sichtbar", "nicht_sichtbar"),
    "vorlaeufig_intern": ("nur_intern_sichtbar", "nicht_sichtbar"),
    "vorlaeufig_sichtbar": ("nur_intern_sichtbar", "nicht_sichtbar", "fuer_empfaenger_sichtbar"),
    "final_freigegeben": ("nur_intern_sichtbar", "nicht_sichtbar", "fuer_empfaenger_sichtbar"),
    "zurueckgezogen": ("nur_intern_sichtbar", "nicht_sichtbar"),
    "ki_vormeldung": ("nur_intern_sichtbar", "nicht_sichtbar"),
}

# Zuordnung zu den lokalen Begriffen - fuer Prueflisten und das Manuskript.
LOKALE_BEFUNDSTATUS_BEZEICHNUNG = {
    "entwurf": "schreiben",
    "vorlaeufig_intern": "lesen",
    "vorlaeufig_sichtbar": "gegenlesen",
    "final_freigegeben": "freigegeben",
    "zurueckgezogen": "zurueckgezogen",
}


class SchemaFehler(ValueError):
    """Verletzung des Aussagenschemas oder Vokabulars (Backend-Pruefung B03)."""


# --------------------------------------------------------------------------- Welt-Entitaeten

@dataclass
class Patient:
    patient_id: str
    anzeigename: str
    geburtsdatum: str
    fallnummer: str


@dataclass
class Studie:
    study_id: str
    patient_id: str
    modalitaet: str
    koerperregion: str
    dringlichkeit: str            # elektiv | akut
    durchgefuehrt_am: datetime
    fragestellung: str
    zuweiser_id: str


@dataclass
class Dokument:
    doc_id: str
    version: int
    doc_typ: str
    patient_id: str
    status: str
    verfasser_rolle: str
    erstellt_am: datetime
    gueltig_ab: datetime
    vertrauensstufe: str
    herkunft: str
    text: str
    study_id: str | None = None
    signiert_von_rolle: str | None = None
    signiert_am: datetime | None = None
    ersetzt_version: int | None = None
    ersetzt_durch_version: int | None = None

    def __post_init__(self) -> None:
        if self.status not in DOKUMENTSTATUS:
            raise SchemaFehler(f"unbekannter Dokumentstatus: {self.status}")
        if self.doc_typ not in DOKUMENTTYPEN:
            raise SchemaFehler(f"unbekannter Dokumenttyp: {self.doc_typ}")
        if self.vertrauensstufe not in VERTRAUENSSTUFEN:
            raise SchemaFehler(f"unbekannte Vertrauensstufe: {self.vertrauensstufe}")
        # Invariante: Signatur genau dann, wenn final freigegeben.
        signiert = self.signiert_von_rolle is not None
        if signiert != (self.status == "final_freigegeben"):
            raise SchemaFehler(
                f"{self.doc_id}@{self.version}: Signatur und Status widersprechen sich "
                f"(status={self.status}, signiert_von_rolle={self.signiert_von_rolle})"
            )

    def kopf(self) -> dict[str, Any]:
        """Metadaten ohne Text - das, was Suchwerkzeuge zurueckgeben."""
        return {
            "doc_id": self.doc_id, "version": self.version, "doc_typ": self.doc_typ,
            "patient_id": self.patient_id, "study_id": self.study_id, "status": self.status,
            "verfasser_rolle": self.verfasser_rolle,
            "signiert_von_rolle": self.signiert_von_rolle,
            "erstellt_am": self.erstellt_am.isoformat(timespec="seconds"),
            "vertrauensstufe": self.vertrauensstufe, "herkunft": self.herkunft,
        }


@dataclass
class Ereignis:
    event_id: str
    ereignis_typ: str
    patient_id: str
    bezug_ref: str
    stattgefunden_am: datetime
    dokumentiert_am: datetime
    dokumentiert_von_rolle: str
    beleg_doc_id: str

    def __post_init__(self) -> None:
        if self.ereignis_typ not in EREIGNISTYPEN:
            raise SchemaFehler(f"unbekannter Ereignistyp: {self.ereignis_typ}")

    def als_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "ereignis_typ": self.ereignis_typ,
            "patient_id": self.patient_id, "bezug_ref": self.bezug_ref,
            "stattgefunden_am": self.stattgefunden_am.isoformat(timespec="seconds"),
            "dokumentiert_am": self.dokumentiert_am.isoformat(timespec="seconds"),
            "dokumentiert_von_rolle": self.dokumentiert_von_rolle,
            "beleg_doc_id": self.beleg_doc_id,
        }


@dataclass
class Empfaenger:
    empfaenger_id: str
    rolle: str
    fallbezug: str                # beteiligt | nicht_beteiligt
    anzeigename: str = ""

    def __post_init__(self) -> None:
        if self.rolle not in EMPFAENGERROLLEN:
            raise SchemaFehler(f"unbekannte Empfaengerrolle: {self.rolle}")


@dataclass
class Empfehlung:
    rec_id: str
    patient_id: str
    quell_doc_id: str
    quell_version: int
    empfohlene_massnahme_text: str
    zielregion: str
    intervall_text: str | None = None      # woertlich oder None - nie erfunden

    def als_dict(self) -> dict[str, Any]:
        return {
            "rec_id": self.rec_id, "patient_id": self.patient_id,
            "quell_doc_id": self.quell_doc_id, "quell_version": self.quell_version,
            "empfohlene_massnahme_text": self.empfohlene_massnahme_text,
            "zielregion": self.zielregion, "intervall_text": self.intervall_text,
        }


# --------------------------------------------------------------------------- Aussage

@dataclass
class Quellenreferenz:
    doc_id: str
    version: int
    belegstelle: str = ""

    def als_dict(self) -> dict[str, Any]:
        return {"doc_id": self.doc_id, "version": self.version, "belegstelle": self.belegstelle}


@dataclass
class Aussage:
    """Strukturierte klinische Aussage."""
    aussage_id: str
    art: str
    befund_code: str
    patient_id: str
    polaritaet: str
    gewissheit: str
    quellen: list[Quellenreferenz] = field(default_factory=list)
    study_id: str | None = None
    koerperregion: str = ""
    lateralitaet: str = "nicht_zutreffend"
    laesion_ref: str | None = None
    bezugszeitpunkt: datetime | None = None
    zeitliche_qualifikation: str = "zeitlich_unbekannt"
    status_typ: str | None = None
    status_wert: str | None = None
    historisch_markiert: bool = False     # ausdrueckliche Kennzeichnung als historische Aussage

    def __post_init__(self) -> None:
        self.pruefe()

    # -- Validierung (Backend B03) -----------------------------------------
    def pruefe(self) -> None:
        if self.art not in AUSSAGEARTEN:
            raise SchemaFehler(f"unbekannte Aussageart: {self.art}")
        if self.befund_code not in GEGENSTANDS_CODES:
            raise SchemaFehler(f"unbekannter befund_code: {self.befund_code}")
        if self.lateralitaet not in LATERALITAET:
            raise SchemaFehler(f"unbekannte Lateralitaet: {self.lateralitaet}")
        if self.zeitliche_qualifikation not in ZEITLICHE_QUALIFIKATION:
            raise SchemaFehler(f"unbekannte zeitliche Qualifikation: {self.zeitliche_qualifikation}")
        if self.polaritaet not in POLARITAET:
            raise SchemaFehler(f"unbekannte Polaritaet: {self.polaritaet}")
        if self.gewissheit not in GEWISSHEIT:
            raise SchemaFehler(f"unbekannte Gewissheit: {self.gewissheit}")
        if (self.polaritaet, self.gewissheit) not in STAERKE:
            raise SchemaFehler(
                f"unzulaessige Kombination polaritaet={self.polaritaet}/"
                f"gewissheit={self.gewissheit}: 'unbestimmt' ist ausschliesslich mit 'unklar' "
                f"kombinierbar und umgekehrt"
            )
        if self.status_typ is not None:
            if self.status_typ not in STATUS_VOKABULAR:
                raise SchemaFehler(f"unbekannter status_typ: {self.status_typ}")
            if self.status_wert not in STATUS_VOKABULAR[self.status_typ]:
                raise SchemaFehler(
                    f"status_wert '{self.status_wert}' ist fuer status_typ "
                    f"'{self.status_typ}' nicht zulaessig"
                )
        elif self.status_wert is not None:
            raise SchemaFehler("status_wert ohne status_typ")

    @property
    def staerke(self) -> int:
        return STAERKE[(self.polaritaet, self.gewissheit)]

    def als_dict(self) -> dict[str, Any]:
        return {
            "aussage_id": self.aussage_id,
            "art": self.art,
            "gegenstand": {
                "befund_code": self.befund_code, "koerperregion": self.koerperregion,
                "lateralitaet": self.lateralitaet, "laesion_ref": self.laesion_ref,
            },
            "zuordnung": {"patient_id": self.patient_id, "study_id": self.study_id},
            "zeitbezug": {
                "bezugszeitpunkt": (
                    self.bezugszeitpunkt.isoformat(timespec="seconds")
                    if self.bezugszeitpunkt else None
                ),
                "zeitliche_qualifikation": self.zeitliche_qualifikation,
            },
            "polaritaet": self.polaritaet,
            "gewissheit": self.gewissheit,
            "staerke": self.staerke,
            "quellen": [q.als_dict() for q in self.quellen],
            "behaupteter_status": (
                {"status_typ": self.status_typ, "status_wert": self.status_wert}
                if self.status_typ else None
            ),
            "historisch_markiert": self.historisch_markiert,
        }

    @staticmethod
    def aus_dict(d: dict[str, Any]) -> "Aussage":
        g = d.get("gegenstand", {})
        z = d.get("zuordnung", {})
        t = d.get("zeitbezug", {})
        s = d.get("behaupteter_status") or {}
        bz = t.get("bezugszeitpunkt")
        return Aussage(
            aussage_id=d["aussage_id"],
            art=d["art"],
            befund_code=g.get("befund_code", ""),
            koerperregion=g.get("koerperregion", ""),
            lateralitaet=g.get("lateralitaet", "nicht_zutreffend"),
            laesion_ref=g.get("laesion_ref"),
            patient_id=z.get("patient_id", ""),
            study_id=z.get("study_id"),
            bezugszeitpunkt=parse_zeit(bz) if bz else None,
            zeitliche_qualifikation=t.get("zeitliche_qualifikation", "zeitlich_unbekannt"),
            polaritaet=d["polaritaet"],
            gewissheit=d["gewissheit"],
            quellen=[Quellenreferenz(**q) for q in d.get("quellen", [])],
            status_typ=s.get("status_typ"),
            status_wert=s.get("status_wert"),
            historisch_markiert=d.get("historisch_markiert", False),
        )


@dataclass
class Arbeitsartefakt:
    artifact_id: str
    artefakt_typ: str
    episode_id: str
    patient_id: str
    erzeugt_durch_aktion: str
    aussagen: list[Aussage] = field(default_factory=list)
    freitext_abschnitte: dict[str, str] = field(default_factory=dict)
    sichtbarkeitsklasse: str = "intern"
    zeit_sim: datetime | None = None
    zusatz: dict[str, Any] = field(default_factory=dict)

    def als_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id, "artefakt_typ": self.artefakt_typ,
            "episode_id": self.episode_id, "patient_id": self.patient_id,
            "erzeugt_durch_aktion": self.erzeugt_durch_aktion,
            "aussagen": [a.als_dict() for a in self.aussagen],
            "freitext_abschnitte": self.freitext_abschnitte,
            "sichtbarkeitsklasse": self.sichtbarkeitsklasse,
            "zeit_sim": self.zeit_sim.isoformat(timespec="seconds") if self.zeit_sim else None,
            "zusatz": self.zusatz,
        }


def aussagen_aus_argumenten(roh: Any) -> list[Aussage]:
    """Konvertiert Werkzeugargumente in validierte Aussagen. Wirft SchemaFehler."""
    if roh is None:
        return []
    if not isinstance(roh, list):
        raise SchemaFehler("'aussagen' muss eine Liste sein")
    ergebnis = []
    gesehen: set[str] = set()
    for eintrag in roh:
        if isinstance(eintrag, Aussage):
            a = eintrag
            a.pruefe()
        elif isinstance(eintrag, dict):
            # Seit 27.09.2026: Ein fehlendes
            # Pflichtfeld oder ein falscher Typ ist ein Schemafehler (B03 mit Rueckmeldung an
            # den Agenten), kein Absturz der Episode. Bis dahin brach z. B. eine Aussage ohne
            # 'aussage_id' die ganze Episode mit KeyError ab.
            try:
                a = Aussage.aus_dict(eintrag)
            except KeyError as exc:
                raise SchemaFehler(f"Pflichtfeld fehlt in einer Aussage: {exc}") from None
            except (TypeError, ValueError, AttributeError) as exc:
                raise SchemaFehler(f"Aussage nicht lesbar: {exc}") from None
        else:
            raise SchemaFehler("Aussage muss Objekt oder Aussage-Instanz sein")
        if a.aussage_id in gesehen:
            raise SchemaFehler(f"doppelte aussage_id: {a.aussage_id}")
        gesehen.add(a.aussage_id)
        ergebnis.append(a)
    return ergebnis


def bindung(werkzeug: str, argumente: dict[str, Any], quellenversionen: list[tuple[str, int]]) -> str:
    """pruef_bindung: Hash der geprueften Aktion."""
    from .common import sha256_text
    roh = (
        werkzeug + "|" + kanonisches_json(argumente) + "|"
        + kanonisches_json(sorted(quellenversionen))
    )
    return sha256_text(roh)
