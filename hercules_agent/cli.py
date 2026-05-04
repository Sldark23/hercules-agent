"""
Hercules Agent CLI
Command-line interface for running the agent.
"""
import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hercules_agent.core.agent_controller import AgentController, AgentConfig
from hercules_agent.providers.litellm_provider import LLMProvider, ProviderFactory
from hercules_agent.gateways.gateway import GatewayManager, Platform, PlatformConfig
from hercules_agent import __version__


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_interactive(agent: AgentController):
    """Run in interactive mode"""
    print(f"\n🜸 Hercules Agent v{__version__}")
    print("Type 'quit' or 'exit' to stop\n")
    
    user_id = "cli_user"
    conversation_id = f"cli_{asyncio.get_event_loop().time()}"
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ["quit", "exit", "/exit"]:
                print("Goodbye!")
                break
            
            if not user_input:
                continue
            
            # Process message
            response = await agent.process_message(
                user_id=user_id,
                conversation_id=conversation_id,
                message_text=user_input
            )
            
            print(f"Hercules: {response}\n")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {e}")


async def run_gateway(agent: AgentController):
    """Run as multi-platform gateway"""
    gateway_manager = GatewayManager(agent)
    
    # Load config
    await gateway_manager.load_config("./config/platforms.json")
    
    # Start all enabled gateways
    await gateway_manager.start_all()
    
    print(f"🜸 Hercules Agent Gateway v{__version__} started")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping gateway...")
        await gateway_manager.stop_all()


def main():
    parser = argparse.ArgumentParser(description="Hercules Agent CLI")
    parser.add_argument("--version", action="version", version=f"Hercules Agent v{__version__}")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    parser.add_argument("--gateway", "-g", action="store_true", help="Run as gateway (multi-platform)")
    parser.add_argument("--model", "-m", default="anthropic/claude-sonnet-4", help="Model to use")
    parser.add_argument("--provider", "-p", default="openrouter", help="Provider to use")
    parser.add_argument("--db-path", default="./data/hercules.db", help="Database path")
    parser.add_argument("--allowed-users", nargs="*", help="Allowed user IDs (whitelist)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Build config
    config = AgentConfig(
        default_model=args.model,
        default_provider=LLMProvider(args.provider),
        db_path=args.db_path,
        allowed_user_ids=set(args.allowed_users) if args.allowed_users else set(),
    )
    
    # Create agent
    agent = AgentController(config)
    
    # Initialize
    asyncio.run(agent.initialize())
    
    # Run
    if args.interactive:
        asyncio.run(run_interactive(agent))
    elif args.gateway:
        asyncio.run(run_gateway(agent))
    else:
        # Default to interactive
        asyncio.run(run_interactive(agent))


if __name__ == "__main__":
    main()