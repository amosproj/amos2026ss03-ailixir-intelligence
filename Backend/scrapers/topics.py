"""Curated disease list that drives literature scraping.

Each entry is one disease/topic to populate the *global* AstraDB literature corpus
with. Fields:

  disease   Canonical, stable tag stored in every chunk's metadata. This is what the
            chat retriever filters on, and what a patient's `relevant_diseases`
            Firestore list references — keep it slug-like and DO NOT rename casually.
  label     Human-readable name.
  icd_prefixes  ICD-10 code prefixes used to map a patient's `Diagnosis` entities
                (which carry `icd_code`) onto this disease (Phase 2 / chat filter).
  keywords  PubMed search terms used at scrape time.

This list is intentionally version-controlled (not Firestore) so the corpus's shape
is reviewable in git. The per-patient relevance index *is* in Firestore (Phase 2).
"""

# `aliases` are lowercase substrings matched against a patient's free-text Diagnosis
# `name` (Graphiti does NOT reliably populate icd_code, and reports are often German),
# so name-based matching — not ICD codes — is the primary mapping signal.
DISEASE_TOPICS = [
    {
        'disease': 'prostate_cancer',
        'label': 'Prostate cancer',
        'icd_prefixes': ['C61'],
        'aliases': ['prostate cancer', 'prostate carcinoma', 'prostate adenocarcinoma',
                    'prostatakarzinom', 'prostata-ca', 'prostatakrebs'],
        'keywords': ['prostate cancer', 'prostate adenocarcinoma', 'PSA prostate'],
    },
    {
        'disease': 'breast_cancer',
        'label': 'Breast cancer',
        'icd_prefixes': ['C50'],
        'aliases': ['breast cancer', 'breast carcinoma', 'mammakarzinom', 'brustkrebs'],
        'keywords': ['breast cancer', 'breast carcinoma'],
    },
    {
        'disease': 'type2_diabetes',
        'label': 'Type 2 diabetes mellitus',
        'icd_prefixes': ['E11'],
        'aliases': ['type 2 diabetes', 'diabetes mellitus type 2', 'diabetes mellitus typ 2',
                    'typ-2-diabetes', 'zuckerkrankheit'],
        'keywords': ['type 2 diabetes mellitus', 'type 2 diabetes management'],
    },
    {
        'disease': 'hypertension',
        'label': 'Essential hypertension',
        'icd_prefixes': ['I10'],
        'aliases': ['hypertension', 'high blood pressure', 'hypertonie', 'bluthochdruck'],
        'keywords': ['essential hypertension', 'high blood pressure treatment'],
    },
]

# Quick lookup: ICD-10 prefix -> disease tag (built once at import).
ICD_PREFIX_TO_DISEASE: dict[str, str] = {
    prefix.upper(): topic['disease']
    for topic in DISEASE_TOPICS
    for prefix in topic.get('icd_prefixes', [])
}


def disease_for_icd(icd_code: str | None) -> str | None:
    """Map a patient's ICD-10 code (e.g. 'C61.9') onto a curated disease tag."""
    if not icd_code:
        return None
    code = icd_code.strip().upper()
    # Longest prefix wins (e.g. 'C61' before 'C6').
    for prefix in sorted(ICD_PREFIX_TO_DISEASE, key=len, reverse=True):
        if code.startswith(prefix):
            return ICD_PREFIX_TO_DISEASE[prefix]
    return None


def disease_for_text(text: str | None) -> str | None:
    """Map a free-text diagnosis name onto a curated disease tag via aliases.

    This is the PRIMARY mapping path: Graphiti stores diagnoses as free-text names
    (often German) and rarely fills in icd_code, so we match on the name. Returns the
    first disease whose alias is a substring of the (lowercased) text.
    """
    if not text:
        return None
    t = text.lower()
    for topic in DISEASE_TOPICS:
        for alias in topic.get('aliases', []):
            if alias in t:
                return topic['disease']
    return None


def diseases_for_diagnosis(name: str | None, icd_code: str | None = None) -> str | None:
    """Resolve a Diagnosis node to a curated disease: prefer ICD, fall back to name."""
    return disease_for_icd(icd_code) or disease_for_text(name)
