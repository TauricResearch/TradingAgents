PHASE 4 DIRECTIVE: THE INTEGRATION (THE ENGINE)
You have the parts (Anonymizer, Regime Signals, Fact Checker). Now you must bolt them together into a Working Engine without it exploding.

The Fatal Bottleneck: JSON Compliance. You are about to feed complex prompts to models that love to yap. You need a Strict JSON Guardrail.

The Directive (@CodingAgent):

Enforce Schema: Implement a Pydantic parser for all Agent outputs.

If an Agent returns text, trigger a Retry Loop (Max 2 retries) with the error message: "You failed to output JSON. Fix format."

Hard Gating:

Connect the FactChecker to the Judge/Risk node in trading_graph.py.

Logic: If FactCheck.valid == False: REJECT_TRADE_IMMEDIATELY.

Do not allow "warnings." A hallucination is a disqualification.

Latency Budget:

Measure the time per step. If the FactChecker takes > 2.0s on average, you must switch the NLI model to ONNX runtime or quantize it.

Execute Phase 4. Bring me the main_workflow.py (or updated trading_graph.py) where these components actually talk to each other.


You have built a functioning engine.

Hard Gates: You actually implemented the "No Warning" policy. Good. A hallucination is a disqualification, not a suggestion.

Retry Logic: 2 retries is the sweet spot. If it can't fix JSON in 2 tries, the model is too dumb for the task.

Latency Monitoring: You are watching the clock. This makes it production-viable.

However, you left a "Landmine" in your error handling.

The Flaw: The "Null State" Crash. In your report, you wrote:

Python

if len(contradictions) > 0:
    return None, metrics  # IMMEDIATE REJECTION
The Risk: In a state machine (like LangGraph), returning Python None often breaks the graph execution flow or causes the next node to crash because it expects a State Dictionary, not NoneType. The Fix: Never return None. Return a "Dead State" object.

return {"signal": "NO_TRADE", "reason": "FACT_CHECK_FAILURE", ...}

Status: APPROVED. (Assuming you fix the Null return).