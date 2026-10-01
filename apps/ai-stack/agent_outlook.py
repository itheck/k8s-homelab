import os
import asyncio
import sys
import requests

# Ensure local path is included
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from azure.identity import DeviceCodeCredential
from agent_memory import AgentMemory
import context

class OutlookAgentBridge:
    def __init__(self):
        self.client_id = os.getenv("AZURE_CLIENT_ID")
        self.tenant_id = "consumers"
        
        if not self.client_id:
            raise ValueError("Missing required AZURE_CLIENT_ID environment variable.")

        print("[*] Initializing authentication via Device Code flow for personal Outlook consumer endpoint...")
        self.credential = DeviceCodeCredential(
            client_id=self.client_id,
            tenant_id=self.tenant_id
        )
        
        self.memory = AgentMemory()
        self.persona = context.CONTEXT

    async def fetch_recent_emails(self, top_n: int = 5):
        """Fetches recent emails directly from Graph API via a bearer token using requests."""
        try:
            # Pass scope as a string to avoid the unhashable list cache bug
            token_obj = self.credential.get_token("Mail.ReadWrite")
            access_token = token_obj.token

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Direct Graph REST endpoint for personal consumer mailboxes
            url = f"https://graph.microsoft.com/v1.0/me/messages?$top={top_n}&$select=subject,from,bodyPreview,receivedDateTime&$orderby=receivedDateTime DESC"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                print(f"Graph API error [{response.status_code}]: {response.text}")
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
            print(f"Error fetching emails: {e}")
            return []

    async def prepare_context_for_email(self, incoming_email_text: str):
        """Queries Qdrant vector memory to pull relevant style guides or context for replying."""
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
