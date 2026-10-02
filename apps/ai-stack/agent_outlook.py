import os
import asyncio
import sys
import requests
import msal

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_memory import AgentMemory
import context

class OutlookAgentBridge:
    def __init__(self, user_email: str = None):
        self.client_id = os.getenv("AZURE_CLIENT_ID")
        self.tenant_id = "consumers"
        self.user_email = user_email

        if not self.client_id:
            raise ValueError("Missing required AZURE_CLIENT_ID environment variable.")

        print(f"[*] Initializing MSAL token cache for account: {self.user_email or 'Default'}...")

        # Persistent token cache file path (unified per user email string)
        self.cache_dir = os.path.expanduser("~/.cache/outlook_bridges")
        os.makedirs(self.cache_dir, exist_ok=True)
        safe_user_name = (self.user_email or "default").replace("@", "_").replace(".", "_")
        self.cache_file = os.path.join(self.cache_dir, f"token_cache_{safe_user_name}.bin")

        self.token_cache = msal.SerializableTokenCache()
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r") as f:
                self.token_cache.deserialize(f.read())

        self.app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self.token_cache
        )
        self.memory = AgentMemory()
        self.persona = getattr(context, "CONTEXT", {})

    def _save_cache(self):
        if self.token_cache.has_state_changed:
            with open(self.cache_file, "w") as f:
                f.write(self.token_cache.serialize())

    def get_access_token(self, scopes):
        accounts = self.app.get_accounts()
        result = None
        if accounts:
            result = self.app.acquire_token_silent(scopes, account=accounts[0])

        if not result or "access_token" not in result:
            print(f"[*] No cached token found for {self.user_email}. Initiating interactive device flow...")
            flow = self.app.initiate_device_flow(scopes=scopes)
            if "message" in flow:
                print(flow["message"])
                sys.stdout.flush()

            # Block and wait for user to authenticate
            result = self.app.acquire_token_by_device_flow(flow)

            if "access_token" in result:
                self._save_cache()
                print(f"[*] Successfully authenticated and saved token cache for {self.user_email}!")
            else:
                raise RuntimeError(f"Authentication failed for {self.user_email}: {result.get('error_description')}")

        return result["access_token"]

    async def fetch_recent_emails(self, user_email: str = None, top_n: int = 5):
        """Fetches recent emails directly from Graph API via a bearer token for the authenticated user session."""
        try:
            target_user = user_email or self.user_email
            access_token = self.get_access_token(["Mail.ReadWrite"])

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"https://graph.microsoft.com/v1.0/me/messages?$top={top_n}&$select=subject,from,bodyPreview,receivedDateTime&$orderby=receivedDateTime DESC"
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                print(f"Graph API error for {target_user} [{response.status_code}]: {response.text}")
                return []

            data = response.json()
            messages = data.get("value", [])

            email_list = []
            for msg in messages:
                sender = "Unknown"
                from_field = msg.get("from")
                if from_field and "emailAddress" in from_field:
                    sender = from_field["emailAddress"].get("address", "Unknown")

                email_list.append({
                    "subject": msg.get("subject", "No Subject"),
                    "from": sender,
                    "preview": msg.get("bodyPreview", ""),
                    "received": msg.get("receivedDateTime", "")
                })
            return email_list
        except Exception as e:
            print(f"Error fetching emails for {user_email}: {e}")
            return []

    async def prepare_context_for_email(self, incoming_email_text: str):
        relevant_memories = self.memory.query_memory(incoming_email_text, limit=3)
        return relevant_memories

async def main():
    bridge = OutlookAgentBridge()
    print("Outlook Agent Bridge initialized successfully.")

    emails = await bridge.fetch_recent_emails(top_n=3)
    print(f"\n--- Successfully Fetched {len(emails)} Emails ---")
    for mail in emails:
        print(f"From: {mail['from']} | Subject: {mail['subject']}")

if __name__ == "__main__":
    asyncio.run(main())
