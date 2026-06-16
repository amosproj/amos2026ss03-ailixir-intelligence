"""
Graphiti retrieval pipeline for querying per-user medical knowledge graphs.

Each patient's knowledge graph is stored under group_id = Firebase UID.
Use pipeline.run_retrieval() as the main entry point.

Quick start:
    from retrieval.pipeline import run_retrieval

    output = await run_retrieval(
        query="What medications is this patient on?",
        user_id="firebase-uid-here",
    )
    print(output.context)
"""
