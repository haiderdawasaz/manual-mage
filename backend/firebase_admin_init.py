# backend/firebase_admin_init.py
"""
Initialises Firebase Admin SDK once at process startup.
All other modules import `db` and `verify_id_token` from here.
"""
from __future__ import annotations

import json
import logging

import firebase_admin
from firebase_admin import auth, credentials, firestore

from config import FIREBASE_CREDENTIALS_JSON

logger = logging.getLogger(__name__)

# ── Initialise once ───────────────────────────────────────────────────────────
_cred_dict: dict = json.loads(FIREBASE_CREDENTIALS_JSON)
_cred = credentials.Certificate(_cred_dict)
firebase_admin.initialize_app(_cred)

db: firestore.firestore.Client = firestore.client()


def verify_id_token(id_token: str) -> dict:
    """
    Verifies a Firebase ID token and returns the decoded claims.
    Raises firebase_admin.auth.InvalidIdTokenError on failure.
    """
    return auth.verify_id_token(id_token)