"""
Domain model for a user's application profile.

A `UserProfile` is the row in the `users` Firestore collection that holds the
fields Firebase Auth does not store (first_name, last_name, server timestamps).
The Firebase UID is both the document id in Firestore and the join key with the
Firebase Auth user record.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserProfile(BaseModel):
    uid: str
    email: EmailStr
    first_name: str
    last_name: str
    created_at: datetime
    updated_at: datetime
