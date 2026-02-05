import os
import json
import getpass
import webbrowser
from pathlib import Path
from urllib.parse import quote
from typing import Dict, Optional
 
import requests
import questionary
from questionary import Choice
 
# =========================
# Config: accounts
# =========================
# Map of account_id -> { "role": "<role-name>", "name": "<friendly-name>" }
ACCOUNTS: Dict[str, Dict[str, str]] = {
    # "423549216380":   {"role": "ZTNAMigration", "name": "q2-ct-production-01"},
    # "142524416173":  {"role": "ZTNAMigration", "name": "q2-ct-production-03"},
    # "241128833394": {"role": "ZTNAMigration", "name": "q2-ct-sharedservices-01"},
    # "905418393581":  {"role": "ZTNAMigration", "name": "q2-ct-centrix-01"},
    # "105357887768":  {"role": "ZTNAMigration", "name": "q2-ct-staging-01"},
    "853973692277": {"role": "limited-admin", "name": "presidio-sandbox"},
}
 
# Your AWS IAM Identity Center (SSO) portal region
SSO_PORTAL_REGION = "us-east-1"
API_URL_TEMPLATE = (
    f"https://portal.sso.{SSO_PORTAL_REGION}.amazonaws.com/federation/credentials"
    "?account_id={account}&role_name={role}"
)
 
CREDENTIALS_PATH = Path.home() / ".aws" / "credentials"
 
# Sentinel values for menu navigation
BACK = "__BACK__"
EXIT = "__EXIT__"
 
# =========================
# Low-level helpers
# =========================
def ensure_bearer_token(existing: Optional[str] = None) -> str:
    """
    Resolve the SSO bearer token from parameter, env(AWS_SSO_BEARER_TOKEN), or prompt.
    """
    token = (existing or os.getenv("AWS_SSO_BEARER_TOKEN") or "").strip()
    if not token:
        token = getpass.getpass("Paste your AWS SSO Bearer token (hidden): ").strip()
    if not token:
        raise SystemExit("No bearer token provided. Aborting.")
    return token
 
 
def fetch_role_credentials(account: str, role: str, bearer_token: str) -> Dict[str, str]:
    """
    Call the SSO federation/credentials API to get session creds for an account/role.
    """
    url = API_URL_TEMPLATE.format(account=account, role=role)
    headers = {"Authorization": f"Bearer {bearer_token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed for {account}/{role}: {resp.status_code} {resp.text}"
        )
    data = resp.json()
    creds = data["roleCredentials"]
    return {
        "aws_access_key_id": creds["accessKeyId"],
        "aws_secret_access_key": creds["secretAccessKey"],
        "aws_session_token": creds["sessionToken"],
    }
 
 
def write_credentials_file(all_creds: Dict[str, Dict[str, str]], path: Path) -> None:
    """
    Write ~/.aws/credentials with a section per account ID.
    """
    lines = []
    for account, creds in all_creds.items():
        lines.append(f"[{account}]")
        lines.append(f"aws_access_key_id = {creds['aws_access_key_id']}")
        lines.append(f"aws_secret_access_key = {creds['aws_secret_access_key']}")
        lines.append(f"aws_session_token = {creds['aws_session_token']}")
        lines.append("")  # blank line
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    print(f"✅ Wrote credentials for {len(all_creds)} account(s) to {path}")
 
 
def get_signin_token(temp_creds: Dict[str, str]) -> str:
    """
    Exchange session creds for a SigninToken (for console federation).
    """
    session_payload = {
        "sessionId": temp_creds["aws_access_key_id"],
        "sessionKey": temp_creds["aws_secret_access_key"],
        "sessionToken": temp_creds["aws_session_token"],
    }
    params = {
        "Action": "getSigninToken",
        "SessionType": "json",
        "Session": json.dumps(session_payload),
    }
    r = requests.get("https://signin.aws.amazon.com/federation", params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"getSigninToken failed: {r.status_code} {r.text}")
    return r.json()["SigninToken"]
 
 
def build_console_login_url(signin_token: str, destination: Optional[str] = None) -> str:
    """
    Build the special federated login URL that sets console cookies.
    """
    dest = destination or "https://console.aws.amazon.com/"
    return (
        "https://signin.aws.amazon.com/federation"
        f"?Action=login&Issuer=sso-federation-script"
        f"&Destination={quote(dest, safe='')}"
        f"&SigninToken={signin_token}"
    )
 
 
def open_console(temp_creds: Dict[str, str], destination: Optional[str] = None) -> None:
    """
    Open the AWS console in the default browser using the given session creds.
    """
    token = get_signin_token(temp_creds)
    url = build_console_login_url(token, destination)
    webbrowser.open(url, new=2)
    print("🌐 Opened AWS Console in your browser.")
 
 
# =========================
# Menus (arrow-key UI)
# =========================
def main_menu() -> str:
    selection = questionary.select(
        "Choose an action:",
        choices=[
            Choice("Write creds (all accounts) → Open console", value="WRITE"),
            Choice("Open console (pick account)", value="OPEN"),
            Choice("Exit", value=EXIT),
        ],
    ).ask()
    if selection is None:
        return EXIT
    return selection
 
 
def account_menu(collected: Dict[str, Dict[str, str]], bearer_token: str) -> Optional[str]:
    """
    Arrow-key menu to pick account. Returns account_id or None if Back.
    Loops so user can open multiple consoles; Back returns to caller; Exit quits program.
    """
    while True:
        # Stable, sorted order by account id
        ids = sorted(ACCOUNTS.keys())
        choices = [
            Choice(
                title=f"{ACCOUNTS[a]['name']}  [{a}]  role={ACCOUNTS[a]['role']}  "
                      f"{'✅' if a in collected else '…'}",
                value=a,
            )
            for a in ids
        ]
        choices += [Choice("Back", value=BACK), Choice("Exit", value=EXIT)]
 
        selection = questionary.select("Select an AWS account:", choices=choices).ask()
        if selection is None:
            # Treat cancel as Back
            return None
        if selection == BACK:
            return None
        if selection == EXIT:
            raise SystemExit(0)
 
        acct_id = selection
        # Ensure creds exist (fetch if needed)
        if acct_id not in collected:
            try:
                role = ACCOUNTS[acct_id]["role"]
                print(f"🔐 Fetching credentials for {acct_id}/{role} ...")
                collected[acct_id] = fetch_role_credentials(acct_id, role, bearer_token)
                print("✅ Credentials ready.")
            except Exception as e:
                print(f"❌ Could not fetch credentials: {e}")
                continue
 
        # Optional destination URL
        dest = questionary.text("Optional Console URL (blank for home):").ask()
        dest = (dest or "").strip() or None
 
        try:
            open_console(collected[acct_id], dest)
        except Exception as e:
            print(f"❌ Failed to open console: {e}")
            continue
        # Loop continues to allow opening another account or Back/Exit.
 
 
def write_creds_flow(bearer_token: str) -> Dict[str, Dict[str, str]]:
    """
    Fetch creds for all accounts and write to ~/.aws/credentials.
    Returns dict of successfully fetched creds.
    """
    collected: Dict[str, Dict[str, str]] = {}
    print("\n=== Writing credentials for all configured accounts ===")
    for acct, meta in ACCOUNTS.items():
        role = meta["role"]
        name = meta["name"]
        try:
            print(f"🔐 {name} [{acct}] role={role} ... ", end="", flush=True)
            creds = fetch_role_credentials(acct, role, bearer_token)
            collected[acct] = creds
            print("✅")
        except Exception as e:
            print(f"❌ {e}")
 
    if collected:
        try:
            write_credentials_file(collected, CREDENTIALS_PATH)
        except Exception as e:
            print(f"❌ Failed to write credentials file: {e}")
    else:
        print("⚠️  No credentials fetched. Nothing to write.")
 
    return collected
 
 
def open_console_flow(bearer_token: str, collected: Optional[Dict[str, Dict[str, str]]] = None) -> None:
    """
    Enter the account picker until user hits Back to return to main menu.
    """
    collected = collected or {}
    _ = account_menu(collected, bearer_token)
    # Back returns to caller
 
 
# =========================
# Program entry
# =========================
def main():
    try:
        bearer_token: Optional[str] = "eyJlbmMiOiJBMjU2R0NNIiwidGFnIjoiSUZxMms5Zjh6V1U0X1NoUyIsImFsZyI6IkEyNTZHQ01LVyIsIml2IjoiemQ4MUFOdDQ4YlVyUjRrQyJ9.AYABeJDotyUlY8SGoYpprEUkNyUAHwABABBEYXRhUGxhbmVTZXNzaW9uAAlQZXJlZ3JpbmUAAQAHYXdzLWttcwBLYXJuOmF3czprbXM6dXMtZWFzdC0xOjI3Njc4NzgzOTY5NjprZXkvNDYwM2MxMmQtNWYwYi00ZWI0LWI3YzktY2NiMDQ4OTEyYzI0ALgBAgEAeNp7IV1vTbu0bMh99b9cbjbHJCuztYZMXB0JYW2zKB6aAShmuCLnXF7ylLpxRpp6JW8AAAB-MHwGCSqGSIb3DQEHBqBvMG0CAQAwaAYJKoZIhvcNAQcBMB4GCWCGSAFlAwQBLjARBAxu7Qv0iLQhM1VXr2oCARCAO71PxvgcYIpNyzfQwwH05ZdnX77oPUvWjm5zEd8ng9GprOc2gArw1fldc-PK4-3FbsDMfmYzv_qpvRiDAgAAAAAMAAAQAAAAAAAAAAAAAAAAALE6heb5lPZ7ATqfQ88iVRD_____AAAAAQAAAAAAAAAAAAAAAQAAACBSr6j3bdMbABhUFmUEDc-0XbuXIxw6jel2wha56wP1jkBW7Pv4tmqPaUAX2ghWNbU.4DR8hK1BTP4w-3__.GJdeuavRgrOucqFviXsecWhJiHWuCG-jsnR-vAA2fWytvyjb0cxihi2-XH1zJ1Os-VGWvlnyfQQQozq6IMxhWeuYGFXDfdlAG_ehLR_TJ380eywqW0sUJJVcEUq2MIEu4LOYNeXm7pOUIibtDozSfIpJnp09tNyxLRN2690qpH9Tg1zwhMc9igp3RRX1YSmzxpqAXGcmNkyLiaPWromZ0lr1w3qBGFn3RP8AB0tw3T_Y2kvajmALxk5M1OV_dO9nLMscnWaXVcdknZ2Kqcj3h7FMx4ZYpMqc1FO5FYcVeP9tPoGSK4N-i6KvqPSJlcwd5F-4QrPC3aR9H2Sn2R4EVtr_cNKwXVyRCiDih4BkDl_7i1TvvFhr1Hn7L8V7-jxaqsLF08rG3bLI1dOYvzykr6NiJEVxHnRUZ-1fduHd2KvHWYnzW_xXfnE49jJXLHMx6OgcEuGecxEDFW6PfFN5_rWAloM7cFE4aHmpeFbJ4lUhKB9IkP8J_-4cLwglQCUzunG3tW1EX_Vk-FlhhGnFqzyGfvYsM2t-ybgYqPeN6pDHQ3QTQW40vVu69ipA9AkyPPkr4w98UjeOqKlD-m8HNePPsolOcLGVSmVcld0YUL1YbnL7IUPjbpBfmDSShNG1kpECuI9bhrr8LAOAHtgzEb4j8wsOQQlo61qe8p_DWo4whKBYPRYDme46Jt5OOj64d-elwgpOU8p8tVhvonZ0NtcYXES28kTfgMEghVxyatHZTF4g.0p_3czW3efWeZAC1YLr1Qg"
        collected: Dict[str, Dict[str, str]] = {}
 
        while True:
            action = main_menu()
            if action == EXIT:
                print("Bye!")
                break
 
            # Resolve bearer token once when needed
            if bearer_token is None:
                try:
                    bearer_token = ensure_bearer_token()
                except SystemExit:
                    bearer_token = None
                    continue
 
            if action == "WRITE":
                collected = write_creds_flow(bearer_token)
                # After writing, jump into the account picker to open console(s)
                open_console_flow(bearer_token, collected)
 
            elif action == "OPEN":
                # Go straight to account picker (will fetch per-account on demand)
                open_console_flow(bearer_token, collected)
 
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
 
 
if __name__ == "__main__":
    main()