"""Pro dashboard (Phase 10): explainability UI over the pipeline artifacts.

The view-model layer (service.py) and recorder are dependency-free; the
FastAPI app needs the ``dashboard`` extra.
"""

from tradingagents.pro.dashboard.recorder import PipelineRecorder, RunRecord

__all__ = ["PipelineRecorder", "RunRecord"]
