#!/usr/bin/env python3
import sys, time
sys.path.insert(0, "/Users/niallsemple/Documents/kimi/workspace/darwin-labs-ai")

from darwin_meta.utils.llm_bridge import LLMBridge

llm = LLMBridge()
print("Testing simple chat...")
t0 = time.time()
try:
    r = llm.chat([{"role": "user", "content": "Say hello in one word"}], max_tokens=20)
    print(f"OK in {time.time()-t0:.1f}s: {r.content[:50]}")
except Exception as e:
    print(f"FAILED: {e}")
