#!/usr/bin/env python3
"""Quick import test for self-improve modules."""
import sys
sys.path.insert(0, "/Users/niallsemple/Documents/kimi/workspace/darwin-labs-ai")

from darwin_meta.self_improve.loop import run_one_cycle
from darwin_meta.self_improve.github_scout import scout
from darwin_meta.self_improve.gap_analyser import analyse_gap
from darwin_meta.self_improve.implementer import implement
from darwin_meta.self_improve.edge_tracker import take_snapshot

print("ALL SELF-IMPROVE IMPORTS OK")
