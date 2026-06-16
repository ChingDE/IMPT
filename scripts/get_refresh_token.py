#!/usr/bin/env python3
"""
get_refresh_token.py  —  ONE-TIME, run on your own laptop (needs a web browser).

Produces the three values for the droplet .env:
    GMAIL_CLIENT_ID
    GMAIL_CLIENT_SECRET
    GMAIL_REFRESH_TOKEN

Setup:
  1. In Google Cloud Console, create an OAuth client (type: Desktop app) and
     download its JSON. Save it next to this script as  client_secret.json
  2. pip install google-auth-oauthlib
  3. python get_refresh_token.py
  4. A browser opens — sign in as novasoft.impt@gmail.com and approve.
     (If you see "Google hasn't verified this app", click Advanced -> Go to app.)
  5. Copy the three printed values into the droplet .env. Do NOT commit them.

Note: the scope is gmail.send only (can send mail, cannot read your inbox).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    # access_type=offline + prompt=consent guarantees a refresh_token is returned.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    print("\n=== Copy these into your droplet .env ===\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print('EMAIL_FROM=IMPT <novasoft.impt@gmail.com>')
    print("\n(Keep these secret — they let the app send mail as your account.)")

if __name__ == "__main__":
    main()
