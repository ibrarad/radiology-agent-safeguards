#!/usr/bin/env python3
"""Explorativ, nachtraeglich (nicht im eingefrorenen Protokoll): An welchem Schritt des agentischen
Workflows entstehen die ausgefuehrten Fehler hoher wirksamer Stufe?

    python3 analysis/22_fehlerorte_workflow.py [--md bericht.md]

Jede Verletzung traegt die Nummer der Aktion, die sie ausgeloest hat (aktion_nr). Das Werkzeug
dieser Aktion bestimmt den Workflow-Schritt. Verletzungen ohne Aktion (z. B. fehlende Klaerung,
festgestellt am Ende) zaehlen zum Schritt "Abschluss".

Zusatzfragen je Fehler:
  - Faktenmanipulation: hatte der Agent das veraenderte Dokument vor der Fehleraktion gelesen?
    ("gelesen und uebernommen" vs. "nicht gelesen")
  - Version (V4): hatte der Agent vor der Fehleraktion die Versionsinformation abgefragt?
Bewertet wird wie in 20_hauptauswertung.py mit versiegeltem Gold und dem Bewerter.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY_ROOT / "src"))
sys.dont_write_bytecode = True
from ragis.evaluator import Bewerter, DIMENSIONSNAMEN                    # noqa: E402

GOLD = STUDY_ROOT / "gold" / "main_sealed"
CASES = STUDY_ROOT / "cases" / "main_sealed"

_REG = json.loads((STUDY_ROOT / "analysis" / "laufregister.json").read_text())
LAEUFE = {info["label"]: info["wiederholungen"]["1"] for info in _REG["modelle"].values()
          if info["wiederholungen"].get("1")}           # seit 10.10.2026 aus dem Laufregister

SCHRITT = {
    "hole_aufgabenpolitik": "1 Auftrag/Regeln",
    **{w: "2 Informationsbeschaffung" for w in (
        "suche_dokumente", "hole_untersuchung", "hole_dokument", "hole_versionsinfo",
        "hole_ereignisse", "pruefe_sichtbarkeit", "suche_empfehlungen", "hole_empfehlung",
        "liste_empfaenger", "hole_arbeitsartefakt")},
    **{w: "3 Artefakt erstellen" for w in (
        "speichere_kommunikationsuebersicht", "speichere_boardvorlage",
        "aktualisiere_nachverfolgung", "speichere_vorbereitungsuebersicht")},
    "dokumentiere_klaerungsbedarf": "4 Klaerung",
    "leite_artefakt_weiter": "5 Weitergabe",
    "melde_abschluss": "6 Abschluss",
}
SCHRITTE = sorted(set(SCHRITT.values()))


def fallendokumente(sid: str) -> set[str]:
    if not sid.endswith("--fm"):
        return set()
    sauber = {d["doc_id"]: d["text"] for d in json.loads(
        (CASES / f"{sid[:-4]}--sauber.json").read_text())["dokumente"]}
    fm = json.loads((CASES / f"{sid}.json").read_text())["dokumente"]
    return {d["doc_id"] for d in fm if sauber.get(d["doc_id"]) != d["text"]}


def fehler(laeufe: list[str]) -> tuple[list[dict], int]:
    zeilen, episoden = [], 0
    for lauf in laeufe:
        for z in open(STUDY_ROOT / "runs" / lauf / "episoden.jsonl", encoding="utf-8"):
            e = json.loads(z)
            if "aufzeichnung" not in e:
                continue
            a = e["aufzeichnung"]; sid = a["szenario_id"]; episoden += 1
            b = Bewerter(json.loads((GOLD / f"{sid}.gold.json").read_text())).bewerte(a)
            akt = {x["nr"]: x for x in a["aktionen"]}
            falle = fallendokumente(sid)
            for v in b["verletzungen"]:
                if not v.get("ausgefuehrt") or v.get("stufe", v["schwere"]) != "hoch":
                    continue
                nr = v.get("aktion_nr")
                werkzeug = akt[nr]["werkzeug"] if nr in akt else "melde_abschluss"
                vorher = [x for x in a["aktionen"] if nr is None or x["nr"] < nr]
                gelesen = {x["argumente"].get("doc_id") for x in vorher
                           if x["werkzeug"] == "hole_dokument"}
                zeilen.append({
                    "modul": a["modul"], "arm": a["arm"], "bedingung": a["bedingung"],
                    "dimension": v["dimension"], "schritt": SCHRITT.get(werkzeug, "?" + werkzeug),
                    "weitergegeben": bool(v.get("aussenwirkung")),
                    "falle_gelesen": (bool(falle & gelesen) if falle else None),
                    "version_abgefragt": (any(x["werkzeug"] == "hole_versionsinfo" for x in vorher)
                                          if v["dimension"] == "V4" else None),
                })
    return zeilen, episoden


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    args = ap.parse_args()
    out = ["# Fehlerorte im agentischen Workflow (explorativ, nachtraeglich)", "",
           "Ausgefuehrte Verletzungen wirksamer Stufe **hoch**, alle Arme. Zuordnung ueber das "
           "Werkzeug der ausloesenden Aktion.", ""]
    alle = {m: fehler(l) for m, l in LAEUFE.items()}

    out += ["## Schritt", "", "| Modell | Episoden | Fehler | " + " | ".join(SCHRITTE) + " |",
            "|---|---:|---:|" + "---:|" * len(SCHRITTE)]
    for m, (z, n) in alle.items():
        c = Counter(x["schritt"] for x in z)
        out.append(f"| {m} | {n} | {len(z)} | " + " | ".join(str(c[s]) for s in SCHRITTE) + " |")

    dims = sorted(DIMENSIONSNAMEN)
    out += ["", "## Dimension", "", "| Modell | " + " | ".join(dims) + " |", "|---|" + "---:|" * len(dims)]
    for m, (z, n) in alle.items():
        c = Counter(x["dimension"] for x in z)
        out.append(f"| {m} | " + " | ".join(str(c[d]) for d in dims) + " |")
    out += ["", "; ".join(f"{d} = {DIMENSIONSNAMEN[d]}" for d in dims)]

    out += ["", "## Schritt x Dimension (alle Modelle)", "",
            "| Schritt | " + " | ".join(dims) + " |", "|---|" + "---:|" * len(dims)]
    sd = defaultdict(Counter)
    for z, _ in alle.values():
        for x in z:
            sd[x["schritt"]][x["dimension"]] += 1
    for s in SCHRITTE:
        out.append(f"| {s} | " + " | ".join(str(sd[s][d]) for d in dims) + " |")

    out += ["", "## Ursache: Information fehlte oder wurde falsch verarbeitet?", "",
            "| Modell | FM-Fehler: Falle vorher gelesen | FM-Fehler: nicht gelesen | "
            "V4: Version vorher abgefragt | V4: nicht abgefragt | weitergegeben |",
            "|---|---:|---:|---:|---:|---:|"]
    for m, (z, n) in alle.items():
        fm = [x for x in z if x["falle_gelesen"] is not None]
        v4 = [x for x in z if x["version_abgefragt"] is not None]
        out.append(f"| {m} | {sum(x['falle_gelesen'] for x in fm)} | "
                   f"{sum(not x['falle_gelesen'] for x in fm)} | "
                   f"{sum(x['version_abgefragt'] for x in v4)} | "
                   f"{sum(not x['version_abgefragt'] for x in v4)} | "
                   f"{sum(x['weitergegeben'] for x in z)} |")

    out += ["", "## Schritt je Modul (alle Modelle)", "", "| Modul | " + " | ".join(SCHRITTE) + " |",
            "|---|" + "---:|" * len(SCHRITTE)]
    sm = defaultdict(Counter)
    for z, _ in alle.values():
        for x in z:
            sm[x["modul"]][x["schritt"]] += 1
    for mod in ("M1", "M2", "M3"):
        out.append(f"| {mod} | " + " | ".join(str(sm[mod][s]) for s in SCHRITTE) + " |")

    text = "\n".join(out) + "\n"
    print(text)
    if args.md:
        with open(args.md, "x", encoding="utf-8") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
