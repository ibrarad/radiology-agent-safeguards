"""Gemeinsame Bausteine: IDs, kanonisches JSON, Pruefsummen, Simulationszeit, Goldsperre.

Die Goldsperre (fsguard): sie ist eine
Anwendungsmassnahme, KEIN betriebssystemseitiger Schutz. Sie wird im agentenseitigen
Prozess aktiviert und protokolliert jeden Zugriffsversuch auf Goldreferenzen.
"""
from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- JSON / Hash

def kanonisches_json(obj: Any) -> str:
    """Stabile Serialisierung fuer Pruefsummen und Bindungen."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_datei(pfad: str | Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def seed_fuer(run_id: str, szenario_id: str, arm: str, modell: str, wiederholung: int) -> int:
    """Reproduzierbarer Seed."""
    roh = f"{run_id}|{szenario_id}|{arm}|{modell}|{wiederholung}"
    return int(sha256_text(roh)[:16], 16)


# --------------------------------------------------------------------------- Simulationszeit

@dataclass
class Simulationsuhr:
    """Klinische Simulationszeit. Ausdruecklich getrennt von Wanduhr und API-Latenz."""
    t0: datetime
    _jetzt: datetime = field(init=False)

    def __post_init__(self) -> None:
        self._jetzt = self.t0

    @property
    def jetzt(self) -> datetime:
        return self._jetzt

    def vorstellen(self, minuten: int = 0, stunden: int = 0, tage: int = 0) -> datetime:
        self._jetzt = self._jetzt + timedelta(minutes=minuten, hours=stunden, days=tage)
        return self._jetzt

    def setze(self, zeitpunkt: datetime) -> None:
        if zeitpunkt < self._jetzt:
            raise ValueError("Simulationszeit darf nicht rueckwaerts laufen")
        self._jetzt = zeitpunkt

    def iso(self) -> str:
        return self._jetzt.isoformat(timespec="seconds")


def parse_zeit(wert: str | datetime) -> datetime:
    if isinstance(wert, datetime):
        return wert
    return datetime.fromisoformat(wert)


# --------------------------------------------------------------------------- Goldsperre

class GoldAccessViolation(RuntimeError):
    """Wird geworfen, wenn der agentenseitige Prozess eine Goldreferenz oeffnen will."""


class _Goldsperre:
    def __init__(self) -> None:
        self.aktiv = False
        self.gesperrte_praefixe: list[str] = []
        self.verstoesse: list[dict[str, str]] = []
        self._orig_builtins_open = None
        self._orig_io_open = None
        self._orig_os_open = None

    def _verletzt(self, pfad: Any) -> str | None:
        try:
            aufgeloest = os.path.realpath(os.fspath(pfad))
        except (TypeError, ValueError):
            return None
        for praefix in self.gesperrte_praefixe:
            if aufgeloest == praefix or aufgeloest.startswith(praefix + os.sep):
                return aufgeloest
        return None

    def _pruefe(self, pfad: Any, quelle: str) -> None:
        treffer = self._verletzt(pfad)
        if treffer is not None:
            self.verstoesse.append({"pfad": treffer, "quelle": quelle})
            raise GoldAccessViolation(
                f"Zugriff auf Goldreferenz aus dem agentenseitigen Prozess verweigert: {treffer} "
                f"(ueber {quelle})."
            )

    def aktiviere(self, *gold_wurzeln: str | Path) -> None:
        self.gesperrte_praefixe = [os.path.realpath(os.fspath(w)) for w in gold_wurzeln]
        if self.aktiv:
            return
        self._orig_builtins_open = builtins.open
        self._orig_io_open = io.open
        self._orig_os_open = os.open
        sperre = self

        def geschuetztes_open(datei, *a, **kw):
            sperre._pruefe(datei, "open")
            return sperre._orig_builtins_open(datei, *a, **kw)

        def geschuetztes_io_open(datei, *a, **kw):
            sperre._pruefe(datei, "io.open")
            return sperre._orig_io_open(datei, *a, **kw)

        def geschuetztes_os_open(pfad, *a, **kw):
            sperre._pruefe(pfad, "os.open")
            return sperre._orig_os_open(pfad, *a, **kw)

        builtins.open = geschuetztes_open
        io.open = geschuetztes_io_open
        os.open = geschuetztes_os_open
        self.aktiv = True

    def deaktiviere(self) -> None:
        if not self.aktiv:
            return
        builtins.open = self._orig_builtins_open
        io.open = self._orig_io_open
        os.open = self._orig_os_open
        self.aktiv = False


GOLDSPERRE = _Goldsperre()


def aktiviere_goldsperre(*gold_wurzeln: str | Path) -> None:
    """Im agentenseitigen Prozess aufrufen, bevor eine Episode startet."""
    GOLDSPERRE.aktiviere(*gold_wurzeln)


# --------------------------------------------------------------------------- Pfadgrenze

class PfadgrenzeVerletzt(RuntimeError):
    pass


def pruefe_innerhalb(pfad: str | Path, wurzel: str | Path) -> Path:
    """Stellt sicher, dass ein Pfad nach Symlink-Aufloesung innerhalb der Wurzel liegt."""
    p = Path(os.path.realpath(os.fspath(pfad)))
    w = Path(os.path.realpath(os.fspath(wurzel)))
    if p != w and w not in p.parents:
        raise PfadgrenzeVerletzt(f"{p} liegt ausserhalb von {w}")
    return p


STUDY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = STUDY_ROOT.parent
