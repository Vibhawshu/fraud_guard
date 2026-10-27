"""
FraudGuard — Gmail Scanner

Fetches emails from your Gmail inbox and sends each one through the
FraudGuard detection API. Results — including subject, sender, and
full LIME reasoning — are saved to the shared SQLite database, so
they appear in the History tab of the web UI.

Prerequisites:
    1. credentials.json in project root (downloaded from Google Cloud Console)
    2. token.json created on first run (OAuth flow)
    3. FastAPI backend running:
           python -m uvicorn backend.main:app --reload

Usage:
    python gmail_scanner.py
    python gmail_scanner.py --max 20
    python gmail_scanner.py --query "is:unread"
    python gmail_scanner.py --query "from:security@paypal.com"
    python gmail_scanner.py --reset-token
"""

import os
import sys
import argparse
import base64
import re
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------- Config ----------
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
API_URL = "http://127.0.0.1:8000/predict"
HEALTH_URL = "http://127.0.0.1:8000/health"


# ---------- Backend health ----------
def check_backend() -> bool:
    try:
        r = requests.get(HEALTH_URL, timeout=3)
        return r.ok
    except requests.exceptions.RequestException:
        return False


# ---------- Auth ----------
def get_gmail_service():
    """Authenticate with Gmail using stored token or fresh OAuth flow."""
    creds = None

    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            print(f"Warning: token.json invalid ({e}). Re-authenticating.")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed ({e}). Starting fresh login.")
                creds = None

        if not creds:
            if not CREDENTIALS_FILE.exists():
                print(f"ERROR: credentials.json not found at {CREDENTIALS_FILE}")
                print("Download it from Google Cloud Console -> APIs & Services -> Credentials.")
                sys.exit(1)

            print("Opening browser for Gmail authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print("Authorization complete. Token saved.\n")

    return build("gmail", "v1", credentials=creds)


# ---------- MIME parsing ----------
def _decode_base64(data: str) -> str:
    """Gmail uses URL-safe base64 without padding. Add padding before decoding."""
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    """Remove script/style blocks, then tags, then collapse whitespace."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&[a-zA-Z]+;", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def extract_body(payload: dict) -> str:
    """Recursively walk a Gmail payload tree and return the best plaintext body."""
    mime = payload.get("mimeType", "")

    if "body" in payload and payload["body"].get("data"):
        raw = _decode_base64(payload["body"]["data"])
        return _strip_html(raw) if mime == "text/html" else raw

    parts = payload.get("parts", [])
    if not parts:
        return ""

    # Prefer text/plain
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode_base64(part["body"]["data"])

    # Then text/html
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return _strip_html(_decode_base64(part["body"]["data"]))

    # Recurse into nested multiparts
    for part in parts:
        body = extract_body(part)
        if body:
            return body

    return ""


def get_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ---------- Classification ----------
def classify_email(text: str, subject: str = None, sender: str = None) -> dict:
    """Send text + metadata to the local FraudGuard API."""
    payload = {
        "text": text,
        "message_type": "email",
        "source": "gmail",
    }
    if subject:
        payload["subject"] = subject[:500]
    if sender:
        payload["sender"] = sender[:300]

    resp = requests.post(API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(
        description="Scan Gmail inbox for fraud with FraudGuard"
    )
    parser.add_argument("--max", type=int, default=10,
                        help="Number of emails to scan (default 10)")
    parser.add_argument("--query", default=None,
                        help="Custom Gmail search query (e.g. 'is:unread')")
    parser.add_argument("--reset-token", action="store_true",
                        help="Delete token.json and re-authenticate")
    args = parser.parse_args()

    if args.reset_token and TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print("Deleted token.json — you will be asked to re-authorize.\n")

    # Backend must be up first
    if not check_backend():
        print(f"ERROR: Cannot reach FraudGuard API at {HEALTH_URL}")
        print("Start it first in another terminal:")
        print("    python -m uvicorn backend.main:app --reload")
        sys.exit(1)

    print(f"FraudGuard backend is online ({HEALTH_URL})\n")

    # Authenticate
    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"ERROR: Gmail authentication failed — {type(e).__name__}: {e}")
        sys.exit(1)

    # Fetch message list
    query = args.query or ""
    label_ids = [] if query else ["INBOX"]

    print(f"Fetching {args.max} emails"
          + (f" matching '{query}'" if query else " from INBOX") + "...")

    try:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                maxResults=args.max,
                labelIds=label_ids,
                q=query,
            )
            .execute()
        )
    except HttpError as e:
        print(f"ERROR: Gmail API call failed — {e}")
        sys.exit(1)

    messages = results.get("messages", [])
    if not messages:
        print("No emails found.")
        return

    print(f"Found {len(messages)} email(s). Analyzing...\n")
    print("=" * 72)

    fraud_count = 0
    safe_count = 0
    skipped = 0
    errors = 0

    for i, msg_ref in enumerate(messages, 1):
        try:
            full = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )
        except HttpError as e:
            print(f"[{i}] SKIPPED — could not fetch ({e})")
            skipped += 1
            continue

        headers = full.get("payload", {}).get("headers", [])
        subject = get_header(headers, "Subject") or "(no subject)"
        sender = get_header(headers, "From") or "(unknown sender)"
        body = extract_body(full.get("payload", {}))

        if not body.strip():
            print(f"[{i}] SKIPPED — no readable body | {subject[:60]}")
            skipped += 1
            continue

        # Cap body at 20,000 chars to keep the API responsive but preserve most content.
        # The web UI will show the full body up to this limit.
        body_capped = body[:20000]

        try:
            result = classify_email(
                body_capped, subject=subject, sender=sender
            )
            label = result["label"].upper()
            conf = round(result["confidence"] * 100)
            is_fraud = result["label"] in ("phishing", "spam")
            icon = "⚠️ " if is_fraud else "✅"

            if is_fraud:
                fraud_count += 1
            else:
                safe_count += 1

            print(f"[{i}] {icon} {label} ({conf}% confidence)")
            print(f"     From:    {sender[:70]}")
            print(f"     Subject: {subject[:70]}")

            # Show top fraud signals for fraud cases
            if is_fraud and result.get("explanation"):
                top = ", ".join(
                    f"{t['token']} ({t['weight']:+.2f})"
                    for t in result["explanation"][:3]
                    if t["weight"] > 0
                )
                if top:
                    print(f"     Signals: {top}")
            print()

        except requests.exceptions.ConnectionError:
            print(f"[{i}] ERROR — Cannot reach {API_URL}")
            print("     Is uvicorn still running?")
            errors += 1
        except requests.exceptions.Timeout:
            print(f"[{i}] ERROR — Request timed out (email too long or API slow)")
            errors += 1
        except requests.exceptions.HTTPError as e:
            print(f"[{i}] ERROR — HTTP {e.response.status_code}: {e.response.text[:100]}")
            errors += 1
        except Exception as e:
            print(f"[{i}] ERROR — {type(e).__name__}: {e}")
            errors += 1

    # Summary
    print("=" * 72)
    print("SUMMARY")
    print(f"  Analyzed:       {fraud_count + safe_count}")
    print(f"  Fraud detected: {fraud_count}")
    print(f"  Safe:           {safe_count}")
    print(f"  Skipped:        {skipped}")
    print(f"  Errors:         {errors}")
    print(f"\nAll results saved to the History tab at http://127.0.0.1:8000")


if __name__ == "__main__":
    main()