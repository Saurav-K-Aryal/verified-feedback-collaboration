# T3 B exact search enumeration

## Paste ready text

Across 640 exact trees both bounds held, full scans began at masses 1/2, 2/3, 3/4 for branching 2, 3, 4, and binary depth eight at mass 1/2 required 16 or 510 expansions depending on dead branch topology, showing that mass alone does not determine cost.

## Table

| Binary depth 8 case, n = 1 exact tree | Exact expansions | Rank floor | L |
|---|---:|---:|---:|
| Mass 1/10, full | 9 | 8 | 800000000/43046721 |
| Mass 1/2, full | 510 | 16 | 2048 |
| Mass 9/10, full | 510 | 16 | 800000000 |
| Mass 1/2, terminal | 16 | 16 | 2048 |


## Limits and what was not established

All cells are exact finite constructed trees. The root is not charged and the goal is charged. Including the root adds one to both the measured count and upper bound. Correct step probability equals one minus dead end mass, so the primary sweep does not isolate mass from path probability. The fixed mass topology contrast does. No asymptotic phase transition or language model search benefit is established. Zero probability edges are never expanded. There are no model requests or model failures. The normalized bound position is descriptive.

## Run record

```json
{
  "planned_cells": 640,
  "completed_cells": 640,
  "failed_cells": 0,
  "bound_violations": 0,
  "uncertainty": "Exact deterministic enumeration, not a sampled estimate; sampling CI not applicable",
  "wall_seconds": 2.050572000007378,
  "finished_utc": "2026-11-18T19:27:14.634712+00:00",
  "primary_table": [
    {
      "branching": 2,
      "depth": 8,
      "dead_end_mass": "1/10",
      "correct_step_probability": "9/10",
      "split": "uniform",
      "topology": "full",
      "nonroot_pops_including_goal": 9,
      "all_pops_including_root_goal": 10,
      "rank_floor": 8,
      "levin_L_exact": "800000000/43046721",
      "levin_L": 18.58445850033502,
      "goal_probability_exact": "43046721/100000000",
      "bound_position": 0.09447814453317077,
      "bound_holds": true,
      "generated_positive_probability_nodes": 19,
      "maximum_frontier": 10,
      "full_tree_nonroot_nodes": 510,
      "full_structural_scan": false,
      "status": "completed",
      "error": "",
      "elapsed_seconds": 3.791700873989612e-05
    },
    {
      "branching": 2,
      "depth": 8,
      "dead_end_mass": "1/2",
      "correct_step_probability": "1/2",
      "split": "uniform",
      "topology": "full",
      "nonroot_pops_including_goal": 510,
      "all_pops_including_root_goal": 511,
      "rank_floor": 16,
      "levin_L_exact": "2048",
      "levin_L": 2048.0,
      "goal_probability_exact": "1/256",
      "bound_position": 0.24311023622047245,
      "bound_holds": true,
      "generated_positive_probability_nodes": 511,
      "maximum_frontier": 256,
      "full_tree_nonroot_nodes": 510,
      "full_structural_scan": true,
      "status": "completed",
      "error": "",
      "elapsed_seconds": 0.0015254169993568212
    },
    {
      "branching": 2,
      "depth": 8,
      "dead_end_mass": "9/10",
      "correct_step_probability": "1/10",
      "split": "uniform",
      "topology": "full",
      "nonroot_pops_including_goal": 510,
      "all_pops_including_root_goal": 511,
      "rank_floor": 16,
      "levin_L_exact": "800000000",
      "levin_L": 800000000.0,
      "goal_probability_exact": "1/100000000",
      "bound_position": 6.175000123500002e-07,
      "bound_holds": true,
      "generated_positive_probability_nodes": 511,
      "maximum_frontier": 165,
      "full_tree_nonroot_nodes": 510,
      "full_structural_scan": true,
      "status": "completed",
      "error": "",
      "elapsed_seconds": 0.001839792006649077
    },
    {
      "branching": 2,
      "depth": 8,
      "dead_end_mass": "1/2",
      "correct_step_probability": "1/2",
      "split": "uniform",
      "topology": "terminal",
      "nonroot_pops_including_goal": 16,
      "all_pops_including_root_goal": 17,
      "rank_floor": 16,
      "levin_L_exact": "2048",
      "levin_L": 2048.0,
      "goal_probability_exact": "1/256",
      "bound_position": 0.0,
      "bound_holds": true,
      "generated_positive_probability_nodes": 17,
      "maximum_frontier": 2,
      "full_tree_nonroot_nodes": 510,
      "full_structural_scan": false,
      "status": "completed",
      "error": "",
      "elapsed_seconds": 2.2958993213251233e-05
    }
  ],
  "rank_definition": "One plus higher-probability siblings plus equal-probability siblings with smaller action label",
  "pop_count": "Root excluded, goal included; goal tested on pop; no state cuts",
  "uniform_full_tree_crossover": [
    {
      "branching": 2,
      "analytic_full_scan_crossover": "1/2",
      "first_tested_full_scan_mass_by_depth": {
        "1": "1/2",
        "2": "1/2",
        "3": "1/2",
        "4": "1/2",
        "5": "1/2",
        "6": "1/2",
        "7": "1/2",
        "8": "1/2"
      },
      "tested_cells": 64,
      "crossover_mismatches": 0
    },
    {
      "branching": 3,
      "analytic_full_scan_crossover": "2/3",
      "first_tested_full_scan_mass_by_depth": {
        "1": "2/3",
        "2": "2/3",
        "3": "2/3",
        "4": "2/3",
        "5": "2/3",
        "6": "2/3",
        "7": "2/3",
        "8": "2/3"
      },
      "tested_cells": 64,
      "crossover_mismatches": 0
    },
    {
      "branching": 4,
      "analytic_full_scan_crossover": "3/4",
      "first_tested_full_scan_mass_by_depth": {
        "1": "3/4",
        "2": "3/4",
        "3": "3/4",
        "4": "3/4",
        "5": "3/4",
        "6": "3/4",
        "7": "3/4",
        "8": "3/4"
      },
      "tested_cells": 64,
      "crossover_mismatches": 0
    }
  ]
}
```

## Frozen protocol

```json
{
  "experiment": "T3-B",
  "not_before_utc": "2026-11-18T19:36:00+00:00",
  "branching": [
    2,
    3,
    4
  ],
  "depths": [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8
  ],
  "dead_end_masses": [
    "0",
    "1/10",
    "1/4",
    "1/3",
    "1/2",
    "2/3",
    "3/4",
    "9/10"
  ],
  "wrong_branch_splits": [
    "uniform",
    "concentrated"
  ],
  "topologies": [
    "terminal",
    "full"
  ],
  "primary_table": [
    [
      2,
      8,
      "1/10",
      "uniform",
      "full"
    ],
    [
      2,
      8,
      "1/2",
      "uniform",
      "full"
    ],
    [
      2,
      8,
      "9/10",
      "uniform",
      "full"
    ],
    [
      2,
      8,
      "1/2",
      "uniform",
      "terminal"
    ]
  ],
  "seed": null,
  "analysis": "Exhaust every frozen deterministic cell. Primary contrasts vary m with p=1-m in a normalized unique-goal tree. Secondary contrasts keep m, p, path probability and depth fixed while changing topology or allocation. Report exact expansions, rank floor, L and position between bounds. A finite grid does not establish an asymptotic phase transition. No inferential CI is applicable to deterministic exhaustive cells.",
  "frozen_utc": "2026-11-18T19:27:12.544770+00:00"
}
```
