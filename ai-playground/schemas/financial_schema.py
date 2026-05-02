FINANCIAL_SCHEMA = {

    # =========================
    # ENTITIES
    # =========================
    "entities": {

        # -------------------------
        # PERSON (USER / CUSTOMER)
        # -------------------------
        "person": {
            "id": "",
            "name": "",
            "type": "individual | business",
            "email": "",
            "phone": ""
        },

        # -------------------------
        # ACCOUNT (BANK / WALLET)
        # -------------------------
        "account": {
            "id": "",
            "type": "bank | credit | wallet",
            "balance": "",
            "currency": "",
            "iban": "",
            "bank_name": ""
        },

        # -------------------------
        # TRANSACTION (CORE NODE)
        # -------------------------
        "transaction": {
            "id": "",
            "type": "payment | transfer | withdrawal | deposit",
            "amount": "",
            "currency": "",
            "datetime": "",
            "status": "pending | completed | failed",
            "description": ""
        },

        # -------------------------
        # MERCHANT / COMPANY
        # -------------------------
        "merchant": {
            "id": "",
            "name": "",
            "category": "retail | food | healthcare | utilities | transport"
        },

        # -------------------------
        # CATEGORY (SPENDING TYPE)
        # -------------------------
        "category": {
            "id": "",
            "name": "food | transport | rent | shopping | bills | entertainment"
        },

        # -------------------------
        # DEVICE (FOR FRAUD / TRACKING)
        # -------------------------
        "device": {
            "id": "",
            "type": "mobile | web | pos",
            "identifier": ""
        },

        # -------------------------
        # LOCATION (OPTIONAL BUT POWERFUL)
        # -------------------------
        "location": {
            "id": "",
            "city": "",
            "country": ""
        },

        # -------------------------
        # DOCUMENT (OCR SOURCE)
        # -------------------------
        "document": {
            "id": "",
            "type": "invoice | receipt | bank_statement",
            "source": "",
            "date": ""
        }
    },

    # =========================
    # RELATIONS (GRAPH EDGES)
    # =========================
    "relations": [

        # -------------------------
        # OWNERSHIP
        # -------------------------
        {"type": "OWNS", "from": "person", "to": "account"},

        # -------------------------
        # TRANSACTION FLOW (CORE)
        # -------------------------
        {"type": "INITIATES", "from": "account", "to": "transaction"},
        {"type": "SENT_FROM", "from": "transaction", "to": "account"},
        {"type": "RECEIVED_BY", "from": "transaction", "to": "account"},

        # -------------------------
        # MERCHANT INTERACTION
        # -------------------------
        {"type": "PAID_TO", "from": "transaction", "to": "merchant"},
        {"type": "PROCESSED_BY", "from": "transaction", "to": "merchant"},

        # -------------------------
        # CATEGORIZATION
        # -------------------------
        {"type": "BELONGS_TO", "from": "transaction", "to": "category"},
        {"type": "TAGGED_AS", "from": "transaction", "to": "category"},

        # -------------------------
        # ACCOUNT-TO-ACCOUNT
        # -------------------------
        {"type": "TRANSFER_TO", "from": "account", "to": "account"},

        # -------------------------
        # TEMPORAL RELATION
        # -------------------------
        {"type": "PRECEDES", "from": "transaction", "to": "transaction"},

        # -------------------------
        # DEVICE / FRAUD SIGNALS
        # -------------------------
        {"type": "USES_DEVICE", "from": "transaction", "to": "device"},
        {"type": "SHARES_DEVICE_WITH", "from": "account", "to": "account"},

        # -------------------------
        # LOCATION CONTEXT
        # -------------------------
        {"type": "OCCURRED_AT", "from": "transaction", "to": "location"},

        # -------------------------
        # DOCUMENT PROVENANCE (OCR)
        # -------------------------
        {"type": "SOURCE_OF", "from": "document", "to": "transaction"},
        {"type": "EXTRACTS", "from": "document", "to": "merchant"},
        {"type": "EXTRACTS", "from": "document", "to": "account"}
    ],

    # =========================
    # METADATA
    # =========================
    "metadata": {
        "confidence": "",
        "created_at": "",
        "ocr_engine": "",
        "llm_model": ""
    }
}