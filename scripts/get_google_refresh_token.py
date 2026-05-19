# get_google_refresh_token.py
# One-time script to generate a Google Ads OAuth2 refresh token.
# Run this once, copy the refresh token into .env, then delete this file.
#
# Usage:
#   python3 get_google_refresh_token.py

import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

CLIENT_ID     = os.environ["GOOGLE_ADS_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_ADS_CLIENT_SECRET"]

SCOPES = ["https://www.googleapis.com/auth/adwords"]

client_config = {
    "installed": {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")

print("\n--- Copy this into your .env ---")
print(f"GOOGLE_ADS_REFRESH_TOKEN={credentials.refresh_token}")
