
# 🧠 1. Global System Architecture


```mermaid
flowchart TD

subgraph Upload_Flow[📥 Document Upload Flow]
A[Document Upload] -->C[Document AI Processor]
C --> D[LLM Extraction / Normalization]

D --> E1[Firestore Structured Store]
D --> E2[Vector DB]
D --> E3[Neo4j Knowledge Graph]
D --> E4[GCS Raw Cache]
end

subgraph Chat_Flow[💬 Chat / RAG Flow]
U[User Query] --> R1[Vector Search]
U --> R2[Graph Query]
U --> R3[Firestore Lookup]
U --> R4[Enrichment Layer]

R1 --> M[Context Aggregation]
R2 --> M
R3 --> M
R4 --> M

M --> L[Gemini Response Generation]
L --> O[Final Answer]
end
```


---
# 🔎 2. RAG Query Pipeline

```mermaid
flowchart TD

Q[User Query] --> A1[Semantic Search]
Q --> A2[Neo4j Graph Query]
Q --> A3[Firestore Exact Lookup]
Q --> A4[External Enrichment]

A1 --> C[Context Aggregation]
A2 --> C
A3 --> C
A4 --> C

C --> D[Prompt Builder]
D --> E[Gemini Pro]
E --> F[Final Answer]
```

---

# 🧠 3. Neo4j Knowledge Graph Flow

```mermaid
flowchart TD

U[User]

U --> R[Lab Report]
U --> M[Medication]

%% Lab Report metadata
R --> D1[Date]
R --> L1[Lab Name]
R --> T1[Test Type]

%% Biomarker
R --> B1[Biomarker]

B1 --> V1[Value]
B1 --> U1[Unit]
B1 --> S1[Status]
B1 --> BR[Reference Range]

BR --> MIN[Min]
BR --> MAX[Max]

%% Medication
M --> D2[Drug Name]
M --> DOSE[Dosage]

%% Relations
U -->|HAS_REPORT| R
U -->|TAKES| M
R -->|CONTAINS| B1
```

---

# 📊 4. Graph Query Execution Flow

```mermaid
flowchart TD

Q[User Question] --> A[Gemini Intent Classifier]

A --> B{Intent Type}

B -->|Trend| T1[Time Series Query]
B -->|Abnormal| T2[Threshold Query]
B -->|Compare| T3[Cross Report Query]
B -->|Summary| T4[Aggregate Query]

T1 --> R[Neo4j Result]
T2 --> R
T3 --> R
T4 --> R
```

---

# 🌐 5. External Enrichment Flow

```mermaid
flowchart TD

A[Detected Medical / Domain Signal] --> B[Trigger Engine]

B --> C{Type}

C -->|Biomarker High/Low| D[PubMed Search]
C -->|Condition Detected| E[MedlinePlus]
C -->|General Query| F[Web Search API]

D --> G[LLM Summarization]
E --> G
F --> G

G --> H[Cache Layer]
H --> I[Enrichment Context]
```

---

# 🧩 6. End-to-End System View (Combined Intelligence Loop)

```mermaid
flowchart TD

subgraph INGEST[Ingestion]
A[Document] --> B[OCR / Parser / Layout]
B --> C[Structured Data + Chunks]
C --> D[Firestore + Vector DB + Neo4j]
end

subgraph QUERY[Reasoning Loop]
U[User Query] --> V1[Vector Search]
U --> V2[Graph Reasoning]
U --> V3[Exact Lookup]
U --> V4[Enrichment]

V1 --> X[Context Builder]
V2 --> X
V3 --> X
V4 --> X

X --> Y[Gemini Pro]
Y --> Z[Answer]
end

D --> V1
D --> V2
D --> V3
```

