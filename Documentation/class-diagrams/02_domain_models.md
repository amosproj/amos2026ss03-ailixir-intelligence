# Class Diagram — Domain Models (`shared/models/`)

Source: `Backend/shared/models/*.py`. Prose reference:
[`code-components/01_shared.md`](../code-components/01_shared.md#models-sharedmodels).
These are the Pydantic models both the API and worker services read/write to
Firestore.

```mermaid
classDiagram
    class Document {
        +str id
        +str uid
        +str domain
        +str title
        +DocumentStatus status
        +list~DocumentFile~ files
        +int file_count
        +int total_bytes
        +str idempotency_key
        +str cypher_gcs_uri
        +str processing_step
        +str graph_query
        +str entities_query
        +datetime created_at
        +datetime updated_at
        +datetime finalized_at
        +datetime deleted_at
        +str error
    }
    class DocumentFile {
        +str file_id
        +str file_name
        +str content_type
        +int size_bytes
        +str gcs_object_path
        +datetime upload_completed_at
    }
    class DocumentStatus {
        <<enumeration>>
        PENDING_UPLOAD
        UPLOADED
        PROCESSING
        EXTRACTED
        FAILED
    }
    Document "1" *-- "many" DocumentFile : files
    Document --> DocumentStatus : status

    class Extraction {
        +str doc_id
        +str uid
        +str document_type
        +float confidence_score
        +dict extracted_fields
        +str raw_text
        +int raw_text_chars
        +bool raw_text_truncated
        +str document_purpose
        +str document_date
        +str episode_body
        +datetime extracted_at
    }
    Extraction ..> Document : doc_id (same id, separate Firestore collection)

    class JourneySummary {
        +str uid
        +str summary
        +int document_count
        +datetime last_updated
        +str last_extraction_id
    }
    JourneySummary ..> Extraction : last_extraction_id

    class UserProfile {
        +str uid
        +str email
        +str first_name
        +str last_name
        +datetime created_at
        +datetime updated_at
    }
    Document ..> UserProfile : uid
    JourneySummary ..> UserProfile : uid

    class LiteraturePaper {
        +str pmid
        +str doi
        +str title
        +list~str~ diseases
        +int chunk_count
        +bool full_text
        +str source
        +datetime embedded_at
        +datetime updated_at
    }

    class ErrorCode {
        <<enumeration>>
        UNAUTHENTICATED
        TOKEN_EXPIRED
        DOCUMENT_NOT_FOUND
        DOCUMENT_NOT_EXTRACTED
        CHAT_RETRIEVAL_FAILED
        CHAT_LLM_EMPTY
        VOICE_UNAUTHORIZED
        "...(30 total — see errors.py)"
    }
    class ErrorDetail {
        +ErrorCode code
        +str message
        +str request_id
    }
    class ErrorResponse {
        +ErrorDetail error
    }
    ErrorResponse *-- ErrorDetail : error
    ErrorDetail --> ErrorCode : code
```

