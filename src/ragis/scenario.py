"""Szenariodefinition und Weltaufbau.

Szenariodateien (cases/) enthalten NUR die beobachtbare Welt. Sie enthalten keine
Goldlabels - keine Felder wie 'ist_angriff', 'korrekte_antwort' oder 'loesung'.
Die Sollwerte liegen getrennt unter gold/.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import parse_zeit
from .model import Dokument, Empfaenger, Empfehlung, Ereignis, Patient, Studie
from .tools import Ausfallplan, Werkzeugschicht
from .world import Umgebungspunkt, Welt

VERBOTENE_SZENARIOFELDER = (
    "ist_angriff", "korrekte_antwort", "loesung", "gold", "erwartete_verletzung", "label",
)


class SzenarioFehler(ValueError):
    pass


def lade_szenario(pfad: str | Path) -> dict[str, Any]:
    with open(pfad, "r", encoding="utf-8") as fh:
        daten = json.load(fh)
    pruefe_keine_goldlabels(daten)
    return daten


def pruefe_keine_goldlabels(obj: Any, pfad: str = "") -> None:
    """Stellt sicher, dass die Szenariodatei keine bequem auslesbaren Goldlabels enthaelt."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in VERBOTENE_SZENARIOFELDER:
                raise SzenarioFehler(
                    f"Szenariodatei enthaelt Goldlabel '{k}' an Position '{pfad}'. "
                    f"Sollwerte gehoeren ausschliesslich nach gold/.")
            pruefe_keine_goldlabels(v, f"{pfad}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            pruefe_keine_goldlabels(v, f"{pfad}[{i}]")


def baue_welt(szenario: dict[str, Any]) -> Welt:
    welt = Welt(t0=parse_zeit(szenario["t0"]), patient_scope=szenario["patient_scope"])

    for p in szenario.get("patienten", []):
        welt.fuege_patient(Patient(**p))
    for s in szenario.get("studien", []):
        s = dict(s)
        s["durchgefuehrt_am"] = parse_zeit(s["durchgefuehrt_am"])
        welt.fuege_studie(Studie(**s))
    for e in szenario.get("empfaenger", []):
        welt.fuege_empfaenger(Empfaenger(**e))
    for d in szenario.get("dokumente", []):
        d = dict(d)
        for feld in ("erstellt_am", "gueltig_ab", "signiert_am"):
            if d.get(feld):
                d[feld] = parse_zeit(d[feld])
        d.setdefault("gueltig_ab", d["erstellt_am"])
        welt.fuege_dokument(Dokument(**d))
    for ev in szenario.get("ereignisse", []):
        ev = dict(ev)
        for feld in ("stattgefunden_am", "dokumentiert_am"):
            ev[feld] = parse_zeit(ev[feld])
        welt.fuege_ereignis(Ereignis(**ev))
    for r in szenario.get("empfehlungen", []):
        welt.fuege_empfehlung(Empfehlung(**r))

    welt.umgebungspunkte = [Umgebungspunkt(**u) for u in szenario.get("umgebungspunkte", [])]
    return welt


def baue_werkzeuge(szenario: dict[str, Any], welt: Welt, episode_id: str) -> Werkzeugschicht:
    return Werkzeugschicht(
        welt=welt,
        episode_id=episode_id,
        agentenrolle=szenario.get("agentenrolle", "radiologie_assistenzsystem"),
        aufgabenpolitik=szenario.get("aufgabenpolitik", {}),
        ausfallplan=[Ausfallplan(**a) for a in szenario.get("ausfallplan", [])],
    )
