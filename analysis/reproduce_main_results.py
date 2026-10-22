#!/usr/bin/env python3
"""Reproduce the main results of the manuscript from data/episode_results.csv.

    python analysis/reproduce_main_results.py              # prints a report
    python analysis/reproduce_main_results.py --out report.md

Statistical method (as prespecified): the base scenario is the unit of analysis. For each agent,
scenario and configuration, outcomes are averaged over the scenario's variants. Risk differences
between configurations are computed within scenario, and 95% CIs use a stratified t-interval with
Satterthwaite degrees of freedom (modules weighted equally, scenarios equally within module).
Pooled estimates first average each scenario over the six agents (exploratory). Odds ratios and the
configuration-by-agent interaction come from a logistic GEE with exchangeable correlation within
base scenario (exploratory). Only the first run of each agent is used.
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

DATA = Path(__file__).resolve().parents[1] / "data" / "episode_results.csv"
AGENTS = ["Claude Sonnet 5.5", "GPT-6.1-Sol", "GLM-5.3", "MiniMax M3", "Gemma-4-31B", "Qwen3.8-27B"]


# ----------------------------------------------------------------------------- interval method

def stratified(values: dict[str, list[float]]) -> tuple[float, float, float]:
    """Mean with modules weighted equally, standard error and Satterthwaite df."""
    modules = [m for m in values if values[m]]
    w = 1 / len(modules)
    est = var = denom = 0.0
    for m in modules:
        x = values[m]; n = len(x); mu = sum(x) / n
        s2 = sum((v - mu) ** 2 for v in x) / (n - 1) if n > 1 else 0.0
        est += w * mu
        part = w * w * s2 / n
        var += part
        denom += part * part / (n - 1) if n > 1 else 0.0
    df = var * var / denom if denom > 0 else float("inf")
    return est, math.sqrt(var), df


def t_interval(values: dict[str, list[float]]) -> tuple[float, float, float]:
    est, se, df = stratified(values)
    if not se:
        return est, est, est
    q = float(stats.t.ppf(0.975, df if math.isfinite(df) else 1e6))
    return est, est - q * se, est + q * se


def scenario_rates(d: pd.DataFrame, outcome: str, condition: str | None = None) -> dict:
    """Rate per (module, base scenario, configuration), averaged over variants."""
    if condition:
        d = d[d["condition"] == condition]
    g = d.groupby(["module", "base_scenario", "configuration"])[outcome].mean()
    return g.to_dict()


def proportions(rates: dict, config: str) -> dict:
    out = defaultdict(list)
    for (m, s, c), v in rates.items():
        if c == config:
            out[m].append(v)
    return out


def differences(rates: dict, c1: str, c2: str) -> dict:
    out = defaultdict(list)
    for (m, s, c), v in rates.items():
        if c == c1 and (m, s, c2) in rates:
            out[m].append(v - rates[(m, s, c2)])
    return out


def pooled_rates(d: pd.DataFrame, outcome: str, condition: str | None = None) -> dict:
    acc = defaultdict(list)
    for a in AGENTS:
        for k, v in scenario_rates(d[d["agent"] == a], outcome, condition).items():
            acc[k].append(v)
    return {k: sum(v) / len(v) for k, v in acc.items() if len(v) == len(AGENTS)}


def fmt(t, sign=False) -> str:
    e, lo, hi = (100 * x for x in t)
    f = "{:+.1f}" if sign else "{:.1f}"
    e, lo, hi = (0.0 if abs(x) < 0.05 else x for x in (e, lo, hi))
    return f"{f.format(e)} (95% CI: {f.format(lo)}, {f.format(hi)})".replace("-", "−")


# ----------------------------------------------------------------------------- GEE

def gee(formula: str, d: pd.DataFrame):
    return smf.gee(formula, groups="base_scenario", data=d, family=sm.families.Binomial(),
                   cov_struct=sm.cov_struct.Exchangeable()).fit()


def contrast(res, plus, minus, half=()) -> np.ndarray:
    names = list(res.params.index); k = np.zeros(len(names))
    for n in plus:
        k[names.index(n)] += 1
    for n in minus:
        k[names.index(n)] -= 1
    for n, w in half:
        k[names.index(n)] += w
    return k


def odds_ratio(res, k) -> str:
    est = float(k @ res.params.values); se = float(np.sqrt(k @ res.cov_params().values @ k))
    return f"{math.exp(est):.2f} (95% CI: {math.exp(est - 1.96 * se):.2f}, {math.exp(est + 1.96 * se):.2f})"


# ----------------------------------------------------------------------------- report

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); args = ap.parse_args()
    all_runs = pd.read_csv(DATA)
    d = all_runs[all_runs["run"] == 1].copy()
    assert len(d) == 1638 and set(d["agent"]) == set(AGENTS)
    out = ["# Reproduction of the main results", "", f"Episodes (first run): {len(d)}", ""]

    out += ["## High-severity error and task success per agent (%)", "",
            "| Agent | Outcome | Permissions only | + Rules | + Rules + LLM checker |", "|---|---|---|---|---|"]
    for a in AGENTS:
        for outcome, name in (("high_severity_error", "High-severity error"), ("task_success", "Task success")):
            r = scenario_rates(d[d["agent"] == a], outcome)
            out.append(f"| {a} | {name} | " + " | ".join(fmt(t_interval(proportions(r, c))) for c in "CED") + " |")

    out += ["", "## Risk differences per agent (percentage points, prespecified)", "",
            "| Agent | Outcome | Rules − permissions | Checker added to rules | Rules + checker − permissions |",
            "|---|---|---|---|---|"]
    for a in AGENTS:
        for outcome, name in (("high_severity_error", "High-severity error"), ("task_success", "Task success")):
            r = scenario_rates(d[d["agent"] == a], outcome)
            out.append(f"| {a} | {name} | " + " | ".join(
                fmt(t_interval(differences(r, c1, c2)), True) for c1, c2 in (("E", "C"), ("D", "E"), ("D", "C"))) + " |")

    out += ["", "## Pooled across agents (exploratory)", ""]
    for outcome, name in (("high_severity_error", "High-severity error"), ("task_success", "Task success")):
        for cond, cname in ((None, "all variants"), ("clean", "clean"), ("misleading", "misleading")):
            r = pooled_rates(d, outcome, cond)
            out.append(f"- {name}, {cname}: permissions only {fmt(t_interval(proportions(r, 'C')))}; "
                       f"rules − permissions {fmt(t_interval(differences(r, 'E', 'C')), True)}; "
                       f"checker added {fmt(t_interval(differences(r, 'D', 'E')), True)}; "
                       f"rules + checker − permissions {fmt(t_interval(differences(r, 'D', 'C')), True)}; "
                       f"rules + checker {fmt(t_interval(proportions(r, 'D')))}")

    g = d.copy()
    g["configuration"] = pd.Categorical(g["configuration"], ["C", "E", "D"])
    g["condition"] = pd.Categorical(g["condition"], ["clean", "misleading"])
    r1 = gee("high_severity_error ~ C(configuration) * C(condition) + C(agent)", g)
    iE = "C(configuration)[T.E]:C(condition)[T.misleading]"; iD = "C(configuration)[T.D]:C(condition)[T.misleading]"
    ec = contrast(r1, ["C(configuration)[T.E]"], [], [(iE, 0.5)])
    de = contrast(r1, ["C(configuration)[T.D]"], ["C(configuration)[T.E]"], [(iD, 0.5), (iE, -0.5)])
    r2 = gee("high_severity_error ~ C(configuration) * C(agent) + C(condition)", g)
    inter = [i for i, n in enumerate(r2.params.index) if n.startswith("C(configuration)") and ":C(agent)" in n]
    L = np.zeros((len(inter), len(r2.params))); L[range(len(inter)), inter] = 1
    w = r2.wald_test(L, scalar=True)
    out += ["", "## Logistic GEE, high-severity error (exploratory)", "",
            f"- Rules vs permissions only, OR {odds_ratio(r1, ec)}",
            f"- Checker added to rules, OR {odds_ratio(r1, de)}",
            f"- Configuration-by-agent interaction: Wald chi2 = {float(w.statistic):.2f}, "
            f"df = {len(inter)}, P = {float(w.pvalue):.2f}"]

    m = d[d["condition"] == "misleading"]
    viol = m["n_high_severity_violations"]
    opened = m["misleading_document_opened"] == 1
    mm = m[m["agent"] == "MiniMax M3"]
    out += ["", "## Error anatomy", "",
            f"- High-severity violations: {int(d['n_high_severity_violations'].sum())}, "
            f"at work product {int(d['n_high_at_work_product'].sum())}, "
            f"at completion {int(d['n_high_at_completion'].sum())}",
            f"- Misleading variants: {int(viol[opened].sum())} of {int(viol.sum())} high-severity violations "
            f"in episodes in which the altered document was opened",
            f"- MiniMax M3: {int(mm.loc[mm['misleading_document_opened'] == 0, 'n_high_severity_violations'].sum())} "
            f"of {int(mm['n_high_severity_violations'].sum())} without opening"]

    out += ["", "## Blocks", ""]
    for c, name in (("E", "Rules"), ("D", "Rules + LLM checker")):
        x = d[d["configuration"] == c]
        j, u = int(x["blocks_justified"].sum()), int(x["blocks_unnecessary"].sum())
        out.append(f"- {name}: {j} of {j + u} blocks justified ({100 * j / (j + u):.0f}%)")

    text = "\n".join(out) + "\n"
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
