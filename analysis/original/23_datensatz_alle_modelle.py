#!/usr/bin/env python3
"""Gemeinsamer Episodendatensatz aller Agentenmodelle und Wiederholungen (nachtraeglich).

    python3 analysis/23_datensatz_alle_modelle.py            # schreibt analysis/daten/episoden_alle_modelle.csv

Welche Laeufe dazugehoeren, steht in analysis/laufregister.json. Bewertet wird wie in
20_hauptauswertung.py mit versiegeltem Gold und dem Bewerter; die Endpunkte sind identisch definiert.
Eine Zeile je Episode. Fehlende oder doppelte Episoden je Modell und Wiederholung werden gemeldet.
"""
from __future__ import annotations

import csv
import json
import sys
from ast import literal_eval
from collections import Counter
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY_ROOT / "src"))
sys.path.insert(0, str(STUDY_ROOT / "faelle"))
sys.dont_write_bytecode = True
from ragis.evaluator import Bewerter                                     # noqa: E402

GOLD = STUDY_ROOT / "gold" / "main_sealed"
CASES = STUDY_ROOT / "cases" / "main_sealed"
REGISTER = STUDY_ROOT / "analysis" / "laufregister.json"
ZIEL = STUDY_ROOT / "analysis" / "daten" / "episoden_alle_modelle.csv"


def preise():
    import importlib.util
    spec = importlib.util.spec_from_file_location("pl", STUDY_ROOT / "faelle" / "pilot_lauf.py")
    pl = importlib.util.module_from_spec(spec); spec.loader.exec_module(pl)
    return pl.PREISTABELLE


SCHREIBEND_ARTEFAKT = {"speichere_kommunikationsuebersicht", "speichere_boardvorlage",
                       "aktualisiere_nachverfolgung", "speichere_vorbereitungsuebersicht"}


def fallendokumente(sid: str) -> set[str]:
    if not sid.endswith("--fm"):
        return set()
    sauber = {d["doc_id"]: d["text"] for d in json.loads(
        (CASES / f"{sid[:-4]}--sauber.json").read_text())["dokumente"]}
    return {d["doc_id"] for d in json.loads((CASES / f"{sid}.json").read_text())["dokumente"]
            if sauber.get(d["doc_id"]) != d["text"]}


def nutzung(protokoll: list[dict], preis) -> dict:
    ein = aus = cache = denk = 0; dauer = 0.0; usd_or = 0.0; or_da = False
    for p in protokoll or []:
        u = p.get("usage") or {}
        if isinstance(u, str):
            try:
                u = literal_eval(u)
            except (ValueError, SyntaxError):
                u = {}
        ein += int(u.get("input_tokens", u.get("prompt_tokens", 0)) or 0)
        aus += int(u.get("output_tokens", u.get("completion_tokens", 0)) or 0)
        cache += int(u.get("cached_tokens", 0) or 0)
        denk += int(u.get("reasoning_tokens", 0) or 0)
        dauer += float(p.get("dauer_s") or 0)
        if p.get("kosten_openrouter_usd") not in (None, "None"):
            usd_or += float(p["kosten_openrouter_usd"]); or_da = True
    if or_da:
        usd = usd_or
    elif preis is not None:
        usd = preis.berechne(max(ein - cache, 0), aus, cache, 0)
    else:
        usd = 0.0
    return {"tokens_ein": ein, "tokens_aus": aus, "tokens_cache": cache, "tokens_denken": denk,
            "dauer_modell_s": round(dauer, 2), "usd": round(usd, 5)}


def zeilen_fuer(modell: str, info: dict, wdh: str, laeufe: list[str], preistab) -> list[dict]:
    out = []
    for lauf in laeufe:
        for z in open(STUDY_ROOT / "runs" / lauf / "episoden.jsonl", encoding="utf-8"):
            e = json.loads(z)
            if "aufzeichnung" not in e:
                continue
            a = e["aufzeichnung"]; sid = a["szenario_id"]
            b = Bewerter(json.loads((GOLD / f"{sid}.gold.json").read_text())).bewerte(a)
            st = b["stufen_ausgefuehrt"]
            falle = fallendokumente(sid)
            gelesen = {x["argumente"].get("doc_id") for x in a["aktionen"] if x["werkzeug"] == "hole_dokument"}
            blk = b["blockierte_fehlversuche"]; unn = b["unnoetige_blockierungen"]
            berechtigt = [x for x in blk if not x.get("waere_referenzkonform")]
            hoch = [v for v in b["verletzungen"] if v.get("ausgefuehrt") and v.get("stufe", v["schwere"]) == "hoch"]
            akt = {x["nr"]: x["werkzeug"] for x in a["aktionen"]}
            # Workflow-Schritt wie analysis/22: Werkzeug der ausloesenden Aktion; ohne Aktion = Abschluss
            schritt = ["artefakt" if akt.get(v.get("aktion_nr")) in SCHREIBEND_ARTEFAKT else "abschluss"
                       for v in hoch]
            out.append({
                "modell": modell, "label": info["label"], "hersteller": info["hersteller"],
                "gewichte": info["gewichte"], "wiederholung": int(wdh), "lauf": lauf,
                "szenario": sid.split("--")[0], "variante": sid, "modul": a["modul"],
                "bedingung": "faktenmanipulation" if sid.endswith("--fm") else "sauber", "arm": a["arm"],
                "hoch": int(bool(b["hauptendpunkt_hoch"])),
                "hoch_mittel": int(bool(st.get("hoch") or st.get("moderat"))),
                "erfolg": int(bool(b["nutzbarkeit"]["erfolg"])),
                "n_hoch_verletzungen": len(hoch),
                "dimensionen_hoch": "|".join(sorted({v["dimension"] for v in hoch})),
                "n_hoch_artefakt": schritt.count("artefakt"), "n_hoch_abschluss": schritt.count("abschluss"),
                "aussenwirkung": int(bool(b["aussenwirkung_ausgefuehrt"])),
                # blockierte_fehlversuche (nicht referenzkonform) und unnoetige_blockierungen
                # (waere referenzkonform gewesen) sind disjunkt (geprueft 08.10.2026)
                "blockaden_gesamt": len(blk) + len(unn),
                "blockaden_berechtigt": len(berechtigt), "blockaden_unnoetig": len(unn),
                "falle_gelesen": (int(bool(falle & gelesen)) if falle else ""),
                "klaerungen": a["kennzahlen"].get("klaerungen_hinterlegt", 0),
                "weiterleitungen": a["kennzahlen"].get("weiterleitungen", 0),
                "werkzeugaufrufe": a["kennzahlen"].get("werkzeugaufrufe", 0),
                "schreibversuche": a["kennzahlen"].get("schreibversuche", 0),
                "ende": a.get("ende_grund", ""),
                **nutzung(e.get("agent_protokoll"), preistab.get(a["modellkennung"])),
            })
    return out


def main() -> int:
    reg = json.loads(REGISTER.read_text())
    preistab = preise()
    alle = []
    for modell, info in reg["modelle"].items():
        for wdh, laeufe in info["wiederholungen"].items():
            if not laeufe:
                continue
            z = zeilen_fuer(modell, info, wdh, laeufe, preistab)
            schluessel = Counter((r["variante"], r["arm"]) for r in z)
            doppelt = sum(1 for c in schluessel.values() if c > 1)
            print(f"{info['label']:20} W{wdh}: {len(z):3d} Episoden, {len(schluessel)} Variante×Arm, "
                  f"{doppelt} doppelt")
            alle += z
    ZIEL.parent.mkdir(exist_ok=True)
    with open(ZIEL, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(alle[0]))
        w.writeheader(); w.writerows(alle)
    print(f"{len(alle)} Zeilen -> {ZIEL.relative_to(STUDY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
