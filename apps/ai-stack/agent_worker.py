import os
import asyncio
import aiohttp
import sys

# Ensure local path is included
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_outlook import OutlookAgentBridge

class AIAgentWorker:
    def __init__(self):
        self.outlook_bridge = OutlookAgentBridge()
        # Point this to your GPU worker node endpoint running vLLM
        self.vllm_endpoint = os.getenv("VLLM_ENDPOINT", "http://gpu-worker.local:8000/v1/completions")
        self.model_name = os.getenv("VLLM_MODEL", "casperhansen/llama-3-8b-instruct-awq")

    async def generate_response_via_vllm(self, system_prompt: str, user_prompt: str) -> str:
        """Sends the compiled context and email to the vLLM worker node for inference."""
        payload = {
            "model": self.model_name,
            "prompt": f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}\n<|assistant|>\n",
            "max_tokens": 512,
            "temperature": 0.3
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.vllm_endpoint, json=payload, timeout=30) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("choices", [{}])[0].get("text", "").strip()
                    else:
                        error_text = await response.text()
                        print(f"vLLM inference error (Status {response.status}): {error_text}")
                        return "Error generating response from inference engine."
        except Exception as e:
            print(f"Failed to connect to vLLM worker node: {e}")
            return "Inference connection timeout."

    async def process_inbox_task(self, target_email_user: str):
        """Fetches unread/recent emails, applies RAG + Persona, and drafts a response."""
        print(f"[*] Polling Outlook inbox for: {target_email_user}")
        emails = await self.outlook_bridge.fetch_recent_emails(target_email_user, top_n=1)
        
        if not emails:
            print("[*] No recent emails found.")
            return

        latest_email = emails[0]
        print(f"\n[+] Processing Email:")
        print(f"    From: {latest_email['from']}")
        print(f"    Subject: {latest_email['subject']}")
        print(f"    Preview: {latest_email['preview']}")

        # 1. Prepare dynamic RAG context from Qdrant based on email preview
        rag_memories = await self.outlook_bridge.prepare_context_for_email(latest_email['preview'])
        
        # 2. Assemble static persona rules from context.py
        persona = self.outlook_bridge.persona
        system_prompt = f"""
        {persona['agent_identity']}
        
        [Tone & Style Guidelines]
        {persona['tone_and_style_guidelines']}
        
        [Email Rules]
        {persona['email_and_message_rules']}
        
        [Relevant Dynamic Memories / Style Adjustments]
        {rag_memories}
        """

        user_prompt = f"Incoming Email from {latest_email['from']}\nSubject: {latest_email['subject']}\nBody: {latest_email['preview']}\n\nDraft a response following Israel's communication style."

        print("\n[*] Sending payload to GPU worker node vLLM endpoint...")
        draft_response = await self.generate_response_via_vllm(system_prompt, user_prompt)
        
        print("\n--- AI Generated Response Draft ---")
        print(draft_response)
        print("-----------------------------------")

async def main():
    worker = AIAgentWorker()
    
    # Define your multiple mailboxes here (or pull from an environment variable)
    # e.g., "israel_heck@outlook.com,thriftlikeheck1@outlook.com"
    target_users_env = os.getenv("TARGET_OUTLOOK_USERS", "israel_heck@outlook.com,thriftlikeheck1@outlook.com")
    target_users = [user.strip() for user in target_users_env.split(",")]
    
    for user in target_users:
        print(f"\n==========================================")
        print(f"[*] Checking inbox for: {user}")
        print(f"==========================================")
        await worker.process_inbox_task(user)

if __name__ == "__main__":
    asyncio.run(main())
