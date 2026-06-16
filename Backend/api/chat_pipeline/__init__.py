"""
Chat query pipeline for the Ailixir API.

Three-step pipeline executed per POST /chat/query:

  Step 1 — Contextualize (LLM)
      Checks whether the user's query references previous conversation history.
      If yes, rewrites it to be fully self-contained so the retrieval step
      works without needing conversation context.
      If no, passes the query through unchanged.

  Step 2 — Retrieve (Graphiti / Neo4j)
      Hybrid semantic+keyword search on the patient's knowledge graph,
      scoped to their Firebase UID (group_id=uid). Returns relevant
      relationship facts (EntityEdge) and medical entities (EntityNode).

  Step 3 — Answer (LLM)
      Formats the retrieved graph facts as a structured context block and
      asks Gemini to produce a natural-language answer. The LLM reasons
      over temporal, relationship-aware facts — not raw text chunks.
"""
