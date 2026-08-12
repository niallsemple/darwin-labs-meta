import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darwin_meta.utils.llm_bridge import LLMBridge
from darwin_meta.agents.explorer import ExplorerAgent
from darwin_meta.agents.statistician import StatisticianAgent
from darwin_meta.agents.sceptic import ScepticAgent
from darwin_meta.agents.ceo import CEOAgent
from darwin_meta.loops.meta_learning import MetaLearningLoop
from laboratory.schema import Discovery
print("ALL IMPORTS OK")
