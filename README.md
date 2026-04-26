# AIlixir Intelligence

AI-powered mobile application to extract, structure, and understand information from unstructured documents across domains.

---

## Overview

**AIlixir Intelligence** is a full-stack, AI-native app that helps users turn complex documents into actionable insights.

Users can:
- Upload or scan documents (e.g. medical reports, invoices)
- Extract structured data using domain-specific schemas
- Store data in a personal knowledge base
- Ask questions about their documents in natural language
- Enrich insights with relevant external knowledge (research, regulations, benchmarks)

---

## Problem

Important information is often locked in unstructured documents:

- Medical reports without clear interpretation  
- Financial data spread across invoices and timesheets  
- Legal documents requiring manual cross-referencing  

**AIlixir Intelligence** solves this by making data structured, connected, and conversational.

---

## Tech Stack

- **Frontend:** React Native (Expo)  
- **Backend:** Python + Google Cloud Run  
- **AI/ML:** Vertex AI, Document AI  
- **Database:** Firestore  
- **Knowledge Layer:** Vector Search / Neo4j  

---

## Miro Board Link For backend Tasks

**Edit**
https://miro.com/welcomeonboard/VEw3bWtiaEJuMFVldndnZFp2WCs0ck5oWnBURUxzU3JsZE1zaElsWmJOQVBteFZibmFvc3h3U0FlczgvRDcvM1lwS2k0WEpuNVdUUFBiM1NXN0xiT0RoSUxQR2Fra2EwMDFqaHZyZmU3Ymx3WmJoSWxPQW91Y1hFcFplL3dNNFdhWWluRVAxeXRuUUgwWDl3Mk1qRGVRPT0hdjE=?share_link_id=286578324277

**View**
https://miro.com/app/board/uXjVHcF54Y8=/?share_link_id=142814163268

---------
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

## Setup

```bash
# clone repository
git clone <repo-url>

# navigate into project
cd <project-folder>

# install dependencies
npm install

# start Expo app
npx expo start
