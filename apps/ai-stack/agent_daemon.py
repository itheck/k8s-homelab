#!/usr/bin/env python3
import os
import sys
import time
import logging
import asyncio
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("agent_daemon")

try:
    from agent_worker import AIAgentWorker
    from agent_memory import AgentMemory
except ImportError as e:
    logger.error(f"Failed to import required local modules: {e}")
    sys.exit(1)


class EmailAgentDaemon:
    def __init__(self):
        self.azure_client_id = os.getenv("AZURE_CLIENT_ID")
        self.vllm_api_key = os.getenv("VLLM_API_KEY")
        self.vllm_endpoint = os.getenv("VLLM_ENDPOINT", "http://10.0.0.61:30472/v1/chat/completions")
        self.vllm_model = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ")
        self.qdrant_host = os.getenv("QDRANT_HOST", "10.0.0.51")
        self.poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

        if not self.azure_client_id:
            raise ValueError("Missing required AZURE_CLIENT_ID environment variable.")

        logger.info("Initializing Qdrant Memory Manager...")
        self.memory = AgentMemory()
        logger.info("Email Agent Daemon initialized successfully.")

    async def run_poll_cycle(self):
        logger.info("Starting 24/7 email polling cycle for all target users...")
        try:
            target_users_env = os.getenv("TARGET_OUTLOOK_USERS", "israel_heck@outlook.com,thriftlikeheck1@outlook.com")
            target_users = [user.strip() for user in target_users_env.split(",")]

            for user in target_users:
                logger.info(f"Processing inbox task for: {user}")
                worker = AIAgentWorker(target_user=user)
                await worker.process_inbox_task()

            logger.info("Polling cycle completed successfully for all accounts.")
        except Exception as e:
            logger.error(f"Error encountered during polling cycle: {e}", exc_info=True)

    async def start(self):
        logger.info(f"Agent daemon running in 24/7 continuous mode (Poll interval: {self.poll_interval}s).")
        while True:
            start_time = time.time()
            await self.run_poll_cycle()

            elapsed = time.time() - start_time
            sleep_time = max(0, self.poll_interval - elapsed)
            logger.info(f"Sleeping for {int(sleep_time)} seconds until next polling cycle...")
            await asyncio.sleep(sleep_time)


async def main():
    daemon = EmailAgentDaemon()
    await daemon.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Daemon execution interrupted by user. Exiting...")
    except Exception as e:
        logger.critical(f"Daemon encountered a fatal unhandled exception: {e}", exc_info=True)
        sys.exit(1)
