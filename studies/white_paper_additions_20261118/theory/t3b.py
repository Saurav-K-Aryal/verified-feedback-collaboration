#!/usr/bin/env python3
"""Exact finite-tree Levin search, not a language model performance study."""
from __future__ import annotations
import csv
import heapq
import time
from fractions import Fraction as F
from common import now, report, setup, write_json

def probabilities(branching, mass, split):
    correct = 1 - mass
    if branching == 2 or split == "uniform":
        wrong = [mass / (branching - 1)] * (branching - 1)
    else:
        wrong = [F(9, 10) * mass] + [mass / (10 * (branching - 2))] * (branching - 2)
    return wrong + [correct]

def enumerate_tree(branching, depth, mass, split, topology):
    probs = probabilities(branching, mass, split)
    p = probs[-1]
    if not 0 < p <= 1:
        raise ValueError("Goal probability must be positive")
    # All wrong action labels precede the correct one, including probability ties.
    step_rank = 1 + sum(q >= p for q in probs[:-1])
    rank_floor = depth * step_rank
    upper = F(depth) / p ** depth
    queue = [(F(0), (), F(1), True)]
    nonroot = 0
    generated = 1
    max_frontier = 1
    while queue:
        priority, path, probability, on_spine = heapq.heappop(queue)
        level = len(path)
        nonroot += int(level > 0)
        if on_spine and level == depth:
            value = F(nonroot)
            return {
                "branching": branching, "depth": depth, "dead_end_mass": str(mass),
                "correct_step_probability": str(p), "split": split, "topology": topology,
                "nonroot_pops_including_goal": nonroot, "all_pops_including_root_goal": nonroot + 1,
                "rank_floor": rank_floor, "levin_L_exact": str(upper), "levin_L": float(upper),
                "goal_probability_exact": str(p ** depth),
                "bound_position": float((value - rank_floor) / (upper - rank_floor)) if upper > rank_floor else 0.0,
                "bound_holds": rank_floor <= value <= upper,
                "generated_positive_probability_nodes": generated, "maximum_frontier": max_frontier,
                "full_tree_nonroot_nodes": sum(branching ** level for level in range(1, depth + 1)),
                "full_structural_scan": nonroot == sum(branching ** level for level in range(1, depth + 1)),
                "status": "completed", "error": "",
            }
        if level == depth or (not on_spine and topology == "terminal"):
            continue
        local = probs if on_spine else [F(1, branching)] * branching
        for action, conditional in enumerate(local):
            if conditional == 0:
                continue
            child = path + (action,)
            child_prob = probability * conditional
            child_spine = on_spine and action == branching - 1
            heapq.heappush(queue, (F(level + 1) / child_prob, child, child_prob, child_spine))
            generated += 1
        max_frontier = max(max_frontier, len(queue))
    raise RuntimeError("Positive-probability goal was not found")

def main():
    cfg, out = setup(__file__, "t3b_protocol.json")
    if cfg is None:
        return
    started = time.monotonic()
    rows = []
    for b in cfg["branching"]:
        for d in cfg["depths"]:
            for text_mass in cfg["dead_end_masses"]:
                for split in cfg["wrong_branch_splits"]:
                    if b == 2 and split == "concentrated":
                        continue  # Identical to uniform when there is one wrong child.
                    for topology in cfg["topologies"]:
                        cell = dict(branching=b, depth=d, dead_end_mass=str(F(text_mass)), split=split, topology=topology)
                        before = time.monotonic()
                        try:
                            row = enumerate_tree(b, d, F(text_mass), split, topology)
                        except Exception as error:
                            row = {**cell, "status": "failed", "error": repr(error)}
                        row["elapsed_seconds"] = time.monotonic() - before
                        rows.append(row)
    keys = sorted(set().union(*(r.keys() for r in rows)))
    with (out / "exact_cells.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    def find(key):
        b, d, m, s, t = key
        return next(r for r in rows if (r["branching"], r["depth"], r["dead_end_mass"], r["split"], r["topology"]) == (b, d, str(F(m)), s, t))
    selected = [find(key) for key in cfg["primary_table"]]
    failed = [r for r in rows if r["status"] != "completed"]
    violations = [r for r in rows if r.get("bound_holds") is False]
    crossovers = []
    for b in cfg["branching"]:
        expected = 1-F(1, b)
        group = [r for r in rows if r["branching"] == b and r["split"] == "uniform" and r["topology"] == "full" and r["status"] == "completed"]
        mismatches = [r for r in group if r["full_structural_scan"] != (F(r["dead_end_mass"]) >= expected)]
        first = {}
        for d in cfg["depths"]:
            observed = [F(r["dead_end_mass"]) for r in group if r["depth"] == d and r["full_structural_scan"]]
            first[str(d)] = str(min(observed)) if observed else None
        crossovers.append({"branching": b, "analytic_full_scan_crossover": str(expected),
                           "first_tested_full_scan_mass_by_depth": first,
                           "tested_cells": len(group), "crossover_mismatches": len(mismatches)})
    summary = {
        "planned_cells": len(rows), "completed_cells": len(rows)-len(failed),
        "failed_cells": len(failed), "bound_violations": len(violations),
        "uncertainty": "Exact deterministic enumeration, not a sampled estimate; sampling CI not applicable",
        "wall_seconds": time.monotonic()-started, "finished_utc": now(), "primary_table": selected,
        "rank_definition": "One plus higher-probability siblings plus equal-probability siblings with smaller action label",
        "pop_count": "Root excluded, goal included; goal tested on pop; no state cuts",
        "uniform_full_tree_crossover": crossovers,
    }
    write_json(out / "summary.json", summary)
    full = find([2, 8, "1/2", "uniform", "full"])
    terminal = find([2, 8, "1/2", "uniform", "terminal"])
    if not failed and not violations and not any(r["crossover_mismatches"] for r in crossovers):
        masses = ", ".join(r["analytic_full_scan_crossover"] for r in crossovers)
        branches = ", ".join(str(r["branching"]) for r in crossovers)
        prose = (f"Across {len(rows)} exact trees both bounds held, full scans began at masses {masses} for branching {branches}, and binary depth eight at mass 1/2 required {terminal['nonroot_pops_including_goal']} or {full['nonroot_pops_including_goal']} expansions depending on dead branch topology, showing that mass alone does not determine cost.")
    else:
        prose = f"Exact enumeration planned {len(rows)} trees and recorded {len(failed)} failed cells and {len(violations)} bound violations, so the proposed bounds were not established by this run."
    table = "| Binary depth 8 case, n = 1 exact tree | Exact expansions | Rank floor | L |\n|---|---:|---:|---:|\n"
    for row in selected:
        table += f"| Mass {row['dead_end_mass']}, {row['topology']} | {row.get('nonroot_pops_including_goal', 'failed')} | {row.get('rank_floor', '')} | {row.get('levin_L_exact', '')} |\n"
    limits = ("All cells are exact finite constructed trees. The root is not charged and the goal is charged. Including the root adds one to both the measured count and upper bound. Correct step probability equals one minus dead end mass, so the primary sweep does not isolate mass from path probability. The fixed mass topology contrast does. No asymptotic phase transition or language model search benefit is established. Zero probability edges are never expanded. There are no model requests or model failures. The normalized bound position is descriptive.")
    report(out, "T3 B exact search enumeration", prose, table, limits, summary)
    write_json(out / "RUN_COMPLETE.json", {"status": "completed_with_failures" if failed else "completed", **summary})
    print(f"T3-B completed {len(rows)-len(failed)}/{len(rows)} cells; {out}")

if __name__ == "__main__":
    main()
