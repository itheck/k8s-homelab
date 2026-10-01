import asyncio
import os
import sys

# Ensure local path is included
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent_daemon import MultiAccountOutlookAgent

async def main():
    print("[*] Forcing manual execution of the multi-account agent cycle...")
    agent = MultiAccountOutlookAgent()
    
    # Run the cycle immediately for both accounts
    await agent.run_cycle()
    print("[*] Manual cycle test completed!")

if __name__ == "__main__":
    asyncio.run(main())
