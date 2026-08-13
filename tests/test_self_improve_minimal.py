#!/usr/bin/env python3
import sys
sys.path.insert(0, "/Users/niallsemple/Documents/kimi/workspace/darwin-labs-ai")

from darwin_meta.self_improve.github_scout import scout
from darwin_meta.self_improve.gap_analyser import analyse_gap
from darwin_meta.self_improve.edge_tracker import take_snapshot
from darwin_meta.utils.llm_bridge import LLMBridge

print("=== MINIMAL SELF-IMPROVE TEST ===")

# 1. Before snapshot
print("\n[1/3] Before snapshot...")
before = take_snapshot("before_test")
print(f"  → {before.total_discoveries} discoveries")

# 2. Scout 1 repo
print("\n[2/3] Scouting 1 repo...")
repos = scout(max_repos=1, max_new_clones=1)
print(f"  → Found: {repos[0].full_name if repos else 'NONE'}")

# 3. Evaluate with LLM
if repos:
    print("\n[3/3] Evaluating gap with local LLM...")
    llm = LLMBridge()
    report = analyse_gap(repos[0], llm)
    print(f"  → useful={report.useful} confidence={report.confidence:.2f}")
    print(f"  → priority={report.priority}")
    print(f"  → gaps: {report.gaps[:2]}")

print("\n=== TEST COMPLETE ===")
