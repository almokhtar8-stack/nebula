#!/usr/bin/env python3
import os, sys, json
from pathlib import Path
from urllib.request import urlopen, Request

# Load .env directly — don't rely on shell environment
def _load_env():
    env = Path(__file__).parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

_load_env()

def send(subject: str, body: str) -> None:
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print(f"[notify] No BREVO_API_KEY in .env\nSubject: {subject}")
        return
    data = json.dumps({
        "sender":      {"name": "Nebula", "email": "almokhtaraljarodi@gmail.com"},
        "to":          [{"email": "almokhtaraljarodi@gmail.com", "name": "Almokhtar"}],
        "subject":     subject,
        "textContent": body,
    }).encode()
    req = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=data,
        headers={
            "api-key":      api_key,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        }
    )
    urlopen(req, timeout=10)
    print(f"[notify] Sent: {subject}")

if __name__ == "__main__":
    send(
        sys.argv[1] if len(sys.argv) > 1 else "Nebula notification",
        sys.argv[2] if len(sys.argv) > 2 else "",
    )
