#!/usr/bin/env python3
import sys
sys.path.insert(0, "/Users/niallsemple/Documents/kimi/workspace/darwin-labs-ai")

from darwin_meta.self_improve.loop import run_one_cycle
from darwin_meta.utils.llm_bridge import LLMBridge

llm = LLMBridge()
result = run_one_cycle(llm=llm, max_repos=1, min_confidence=0.75, max_implementations=1)
print("DONE")
print(result)
