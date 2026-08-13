#!/usr/bin/env python3
import sys
sys.path.insert(0, "/Users/niallsemple/Documents/kimi/workspace/darwin-labs-ai")

from darwin_meta.self_improve.github_scout import scout

repos = scout(max_repos=2, max_new_clones=1)
print(f"SCOUTED: {len(repos)} repos")
for r in repos:
    print(f"  {r.full_name} ({r.stars}*) lang={r.language}")
