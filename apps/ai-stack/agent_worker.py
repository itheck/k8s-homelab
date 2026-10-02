import os
import asyncio
import aiohttp
import sys

# Ensure local path is included
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_outlook import OutlookAgentBridge

class AIAgentWorker:
    def __init__(self, target_user: str):
        self.target_user = target_user
        # Initialize the bridge tied to this specific user account
        self.outlook_bridge = OutlookAgentBridge(user_email=target_user)
        self.vllm_endpoint = os.getenv("VLLM_ENDPOINT", "http://10.0.0.61:30472/v1/chat/completions")
        self.model_name = os.getenv("VLLM_MODEL", "casperhansen/llama-3-8b-instruct-awq")
        self.vllm_api_key = os.getenv("VLLM_API_KEY", "")

    async def generate_response_via_vllm(self, system_prompt: str, user_prompt: str) -> str:
        """Sends the compiled context and email to the vLLM worker node using the OpenAI-compatible chat endpoint."""
        headers = {
            "Content-Type": "application/json"
        }
        if self.vllm_api_key:
            headers["Authorization"] = f"Bearer {self.vllm_api_key}"

        # Format payload using standard OpenAI chat messages array expected by vLLM
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 512,
            "temperature": 0.3
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.vllm_endpoint, json=payload, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        result = await response.json()
                        # Extract text from standard chat completion choices structure
                        choices = result.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "").strip()
                        return ""
                    else:
                        error_text = await response.text()
                        print(f"vLLM inference error (Status {response.status}): {error_text}")
                        return "Error generating response from inference engine."
        except Exception as e:
            print(f"Failed to connect to vLLM worker node: {e}")
            return "Inference connection timeout."

    async def process_inbox_task(self):
        """Fetches unread/recent emails, applies RAG + Persona, and drafts a response."""
        print(f"[*] Polling Outlook inbox for: {self.target_user}")
        emails = await self.outlook_bridge.fetch_recent_emails(user_email=self.target_user, top_n=1)

        if not emails:
            print(f"[*] No recent emails found for {self.target_user}.")
            return

        latest_email = emails[0]
        print(f"\n[+] Processing Email for {self.target_user}:")
        print(f"    From: {latest_email['from']}")
        print(f"    Subject: {latest_email['subject']}")
        print(f"    Preview: {latest_email['preview']}")

        # 1. Prepare dynamic RAG context from Qdrant based on email preview
        rag_memories = await self.outlook_bridge.prepare_context_for_email(latest_email['preview'])

        # 2. Assemble static persona rules from context.py
        persona = self.outlook_bridge.persona
        system_prompt = f"""
        {persona.get('agent_identity', 'You are a helpful AI assistant.')}

        [Tone & Style Guidelines]
        {persona.get('tone_and_style_guidelines', '')}

        [Email Rules]
        {persona.get('email_and_message_rules', '')}

        [Relevant Dynamic Memories / Style Adjustments]
        {rag_memories}
        """

        user_prompt = f"Incoming Email from {latest_email['from']}\nSubject: {latest_email['subject']}\nBody: {latest_email['preview']}\n\nDraft a response following the communication guidelines."

        print("\n[*] Sending payload to GPU worker node vLLM endpoint...")
        draft_response = await self.generate_response_via_vllm(system_prompt, user_prompt)

        print(f"\n--- AI Generated Response Draft for {self.target_user} ---")
        print(draft_response)
        print("-------------------------------------------------------")

async def main():
    target_users_env = os.getenv("TARGET_OUTLOOK_USERS", "israel_heck@outlook.com,thriftlikeheck1@outlook.com")
    target_users = [user.strip() for user in target_users_env.split(",")]

    for user in target_users:
        print(f"\n==========================================")
        print(f"[*] Initializing Worker for inbox: {user}")
        print(f"==========================================")
        worker = AIAgentWorker(target_user=user)
        await worker.process_inbox_task()

if __name__ == "__main__":
    asyncio.run(main())
