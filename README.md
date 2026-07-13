# AIlixir Intelligence

## Table of Contents

- [About AIlixir Intelligence](#about-ailixir-intelligence)
- [Tech Stack](#tech-stack)
- [Setup](#setup)
- [Key Features](#key-features)
- [Demo Domains](#demo-domains)

---

## About AIlixir Intelligence

**AIlixir Intelligence** is a domain-agnostic, RAG-powered data context platform that provides an LLM-powered chat interface. It enables users to upload professional data—such as medical or financial documents that are technically readable but practically opaque—and gain valuable insights through conversational querying.

The system extracts structured information, stores it within a personal knowledge base, and enables RAG (Retrieval-Augmented Generation) with optional enrichment from external knowledge sources like research papers.

---

## Tech Stack

- **Frontend:** React Native (Expo), [ElevenLabs](https://elevenlabs.io/) (Voice Chat)
- **Backend:** Python (FastAPI) + Google Cloud Run — one public API service, one internal Pub/Sub-driven worker service, one scheduled batch job
- **Authentication:** Firebase Authentication (ID token validation for API access)
- **AI/ML:** Vertex AI (Gemini — multimodal document analysis, chat, and knowledge-graph extraction via [Graphiti](https://github.com/getzep/graphiti)), OpenAI embeddings + Vertex AI Ranking API (research-paper retrieval)
- **Database:** Firestore (documents, extractions, users)
- **Knowledge Layer:** Neo4j (temporal knowledge graph, per patient), AstraDB (research-paper vector search)

> Full architecture, code-level, and run-it-yourself documentation lives in
> [`Documentation/`](./Documentation) — see its
> [README](./Documentation/README.md) for the index; that's the door into
> exploring the rest of the project.

---

## Setup

### Prerequisites

- Node.js (v18+)
- npm
- [Xcode](https://developer.apple.com/xcode/) (for iOS simulator) or [Android Studio](https://developer.android.com/studio) (for Android emulator)

### Quick Start

```bash
# Clone repository
git clone git@github.com:amosproj/amos2026ss03-ailixir-intelligence.git

# Navigate to frontend
cd frontend/ailixir

# Install dependencies
npm install

# Start the app (iOS)
npm run ios

# Start the app (Android)
npm run android
```

> **Note:** For detailed setup instructions, including backend configuration, environment variables, and Firebase setup, see the [Documentation](./Documentation) or the [Backend README](./Backend/README.md).

---

## Key Features

- Document scanning and upload  
- AI-powered data extraction  
- Domain-configurable architecture (e.g. medical, finance)  
- Chat interface grounded in user data  
- Integration of external knowledge sources  

---

## Demo Domains

- Medical (lab reports, blood results)  
- Finance (invoices, timesheets, expenses)  

---
