```mermaid
graph LR

%% =========================
%% CORE ENTITIES
%% =========================

PERSON[👤 Person]
ACCOUNT[🏦 Account]
TRANSACTION[💳 Transaction]
MERCHANT[🛍 Merchant]
CATEGORY[📊 Category]
DEVICE[📱 Device]
LOCATION[📍 Location]
DOCUMENT[🧾 Document]

%% =========================
%% CORE OWNERSHIP FLOW
%% =========================

PERSON -->|OWNS| ACCOUNT

%% =========================
%% TRANSACTION FLOW
%% =========================

ACCOUNT -->|INITIATES| TRANSACTION
TRANSACTION -->|SENT_FROM| ACCOUNT
TRANSACTION -->|RECEIVED_BY| ACCOUNT

TRANSACTION -->|PAID_TO| MERCHANT
TRANSACTION -->|BELONGS_TO| CATEGORY

%% =========================
%% CONTEXT LAYER
%% =========================

TRANSACTION -->|USES_DEVICE| DEVICE
TRANSACTION -->|OCCURRED_AT| LOCATION

%% =========================
%% PROVENANCE LAYER
%% =========================

DOCUMENT -->|SOURCE_OF| TRANSACTION
DOCUMENT -->|EXTRACTS| MERCHANT
DOCUMENT -->|EXTRACTS| ACCOUNT
mermaid```