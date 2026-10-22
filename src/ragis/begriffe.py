"""Oeffentliche Begriffssystematik: Stichworte je Befundcode und Normalisierung.

Diese Tabelle ist Teil des OEFFENTLICHEN Schemas (wie die Befundcodes selbst), nicht Teil der
Goldreferenz. Sie enthaelt keine fallbezogenen Sollwerte und wurde nicht fuer Haupttestfaelle
geschrieben. Sie wird von mehreren Komponenten genutzt; jede Aenderung ist vor Freeze zu
dokumentieren.
"""
from __future__ import annotations

import re

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                          "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def normalisiere(text: str) -> str:
    return text.translate(_UMLAUTE).lower()


STICHWORTE: dict[str, tuple[str, ...]] = {
    "LUNGENEMBOLIE": ("lungenembolie", "lungenarterienembolie", "pulmonalarterienembolie", "lae"),
    "RECHTSHERZBELASTUNG": ("rechtsherzbelastung", "rechtsherzbelastungszeichen", "rv-belastung"),
    "PLEURAERGUSS": ("pleuraerguss", "erguss"),
    "PNEUMONISCHES_INFILTRAT": ("pneumonie", "infiltrat", "pneumonisches infiltrat"),
    "INTRAKRANIELLE_RAUMFORDERUNG": ("raumforderung", "tumor", "intrakranielle raumforderung"),
    "ZEREBRALE_METASTASE": ("hirnmetastase", "zerebrale metastase"),
    "KNOCHENMETASTASE": ("knochenmetastase", "osteolyse", "ossaere metastase"),
    "PERITONEALKARZINOSE": ("peritonealkarzinose",),
    "NIERENRAUMFORDERUNG": ("nierentumor", "nierenzellkarzinom", "nierenraumforderung"),
    "SCHILDDRUESENKNOTEN": ("schilddruesenknoten", "knoten"),
    "APPENDIZITIS": ("appendizitis", "blinddarmentzuendung"),
    "MILZINFARKT": ("milzinfarkt",),
    "LUNGENRUNDHERD": ("rundherd", "lungenherd", "nodulus", "pulmonaler herd"),
    "PNEUMOTHORAX": ("pneumothorax",),
    "INTRAKRANIELLE_BLUTUNG": ("intrakranielle blutung", "blutung", "haemorrhagie"),
    "AORTENDISSEKTION": ("dissektion", "aortendissektion"),
    # Organbezug ist zwingend: das generische "metastase" traf sonst auch in
    # "metastasenverdaechtiger Rundherd" der Lunge und ordnete den Befund der Leber zu.
    "LEBERLAESION_UNSPEZIFISCH": ("leberlaesion", "leberherd", "leberrundherd",
                                  "leberbefund", "lebersegment"),
    "LEBERLAESION_METASTASENVERDAECHTIG": ("lebermetastase", "leberlaesion", "leberherd",
                                           "leberfiliae", "lebersegment"),
    "NEBENNIERENRAUMFORDERUNG": ("nebenniere", "nebennierenraumforderung", "adenom"),
    "LYMPHKNOTEN_VERGROESSERT": ("lymphknoten", "lymphadenopathie"),
    "NIERENZYSTE": ("nierenzyste", "zyste"),
    "FREIE_LUFT_ABDOMINELL": ("freie luft", "pneumoperitoneum"),
    "FRAKTUR": ("fraktur", "bruch"),
    "ZIELREGION_NICHT_BEURTEILBAR": ("nicht beurteilbar", "nicht ausreichend beurteilbar"),

    # --- Gegenstaende des Transfertests T1 (Voraussetzungen, keine Befunde) -----------
    # Vorab festgelegt, bevor die T1-Faelle verfasst werden. Aenderungen danach sind vor
    # dem Freeze zu dokumentieren.
    "INDIKATION_DOKUMENTIERT": ("indikation", "indikationsstellung", "rechtfertigend"),
    "AUFKLAERUNG_EINWILLIGUNG": ("aufklaerung", "einwilligung", "einverstaendnis",
                                 "aufklaerungsgespraech", "einwilligungserklaerung"),
    # "gerinnung" allein traf auch "gerinnungshemmend" und ordnete Aussagen zum
    # Gerinnungsstatus Belegen ueber die Medikation zu. Deshalb nur spezifische Formen.
    "GERINNUNGSSTATUS": ("gerinnungsstatus", "gerinnungswerte", "gerinnungsanalyse",
                         "quick", "inr", "ptt", "aptt"),
    "THROMBOZYTENZAHL": ("thrombozyten", "thrombozytenzahl", "plaettchen"),
    "GERINNUNGSHEMMENDE_MEDIKATION": ("antikoagulation", "antikoagulanz",
                                      "gerinnungshemmer", "gerinnungshemmend",
                                      "thrombozytenaggregationshemmer", "blutverduenner"),
    "NIERENFUNKTION": ("nierenfunktion", "kreatinin", "egfr", "gfr", "retentionswerte"),
    # Ohne Mittelbezug traf "allergie" auch eine Penicillinallergie.
    "KONTRASTMITTELUNVERTRAEGLICHKEIT": ("kontrastmittelunvertraeglichkeit",
                                         "kontrastmittelallergie", "kontrastmittelreaktion",
                                         "kontrastmittelzwischenfall", "jodallergie"),
    "SCHILDDRUESENFUNKTION": ("schilddruese", "schilddruesenfunktion", "tsh",
                              "hyperthyreose"),
    # "infekt" allein traf auch "desinfektion".
    "INFEKTSTATUS_ANTIBIOTIKAPLAN": ("infektstatus", "infektzeichen", "entzuendungswerte",
                                     "crp", "antibiose", "antibiotikaprophylaxe",
                                     "antibiotikaplan"),
    "SCHWANGERSCHAFTSSTATUS": ("schwangerschaft", "schwangerschaftstest", "gravidit"),
    # "karenz" allein traf auch die Antikoagulationspause.
    "NUECHTERNHEIT": ("nuechtern", "nuechternheit", "nahrungskarenz"),
    "ZUGANGSWEG_BILDGEBUNG": ("zugangsweg", "punktionsweg", "gefaesszugang",
                              "zugangsplanung", "punktionsstelle"),
    "VORBEFUND_AKTUELL": ("vorbefund", "voruntersuchung", "vorbildgebung"),
    "PLANUNGSENTSCHEIDUNG_KONFERENZ": ("konferenzbeschluss", "boardbeschluss",
                                       "konferenzentscheidung", "interdisziplinaere "
                                       "festlegung"),
    "VORAUSSETZUNG_NICHT_BEURTEILBAR": ("nicht beurteilbar", "nicht ausreichend beurteilbar"),
}


# Wortgrenzenregel:
#   Kurze Stichworte (<= 4 Zeichen, typischerweise Abkuerzungen wie "lae") muessen als
#   VOLLSTAENDIGES Wort auftreten. Andernfalls treffen sie als Teilzeichenkette in
#   "vorlaeufig", "laesion" oder "abklaerungsbeduerftig" und erzeugen Falschtreffer.
#   Laengere Stichworte werden als Teilzeichenkette gesucht, weil deutsche Komposita das
#   Stichwort sowohl vorn als auch hinten tragen koennen: "Lungenembolieverdacht" traegt es
#   vorn, "Lungenrundherd" traegt "rundherd" hinten. Eine Wortanfangsregel wuerde den
#   zweiten Fall uebersehen.
_MUSTER: dict[str, tuple[re.Pattern[str], ...]] = {
    code: tuple(
        re.compile(rf"\b{re.escape(w)}\b" if len(w) <= 4 else re.escape(w))
        for w in worte
    )
    for code, worte in STICHWORTE.items()
}


def enthaelt(text_normalisiert: str, code: str) -> bool:
    """Prueft, ob ein Befundcode im normalisierten Text lexikalisch vorkommt."""
    return any(m.search(text_normalisiert) for m in _MUSTER.get(code, ()))


def erkannte_codes(text: str) -> list[str]:
    """Rein lexikalische Erkennung. Keine Bedeutungsanalyse, keine Gewissheitsbewertung."""
    n = normalisiere(text)
    return sorted({code for code in STICHWORTE if enthaelt(n, code)})
