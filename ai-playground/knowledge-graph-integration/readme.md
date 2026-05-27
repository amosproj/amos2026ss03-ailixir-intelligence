# Graphiti Patient Pipeline — How It Works

## Temporal Design
Graphiti tracks `valid_at` / `invalid_at` on every entity and relationship, so the graph naturally handles diagnoses changing, medications being stopped, and lab values updating over time.

---

## What happens on every `add_episode`

```
New document
    │
    ▼
1. EXTRACT    LLM pulls entities + relationships from episode_body
    │
    ▼
2. SEARCH     Vector search for similar existing nodes (scoped to group_id)
    │
    ▼
3. RESOLVE    LLM decides: same entity → MERGE, new entity → CREATE
    │
    ▼
4. EDGES      Create/update relationships with valid_at / invalid_at
    │
    ▼
5. INVALIDATE Changed facts get invalid_at = now, new edge with valid_at = now
```

---

## The three mechanisms

| Mechanism | Job | Without it |
|---|---|---|
| **Patient header** | LLM always extracts the same entity name | "the patient" vs "Mr. Schmidt" → duplicate nodes |
| **`group_id`** | Scopes resolution search to this patient only | Risk of merging entities across patients |
| **`episode_name`** | Provenance tracking only | Lose traceability, nothing else breaks |

They chain together: header ensures consistent naming → `group_id` fences the search → LLM merges confidently.

---

## Scale

Cost grows with existing node count, not just new document size. Runs well up to **~200 documents per patient**. Beyond that: split `group_id` by phase (e.g. `mrn_preop`, `mrn_postop`) and add Neo4j indexes on `group_id` and `name`.