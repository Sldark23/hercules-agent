# Hercules Agent Framework

A modular Python framework for building AI agents with support for multiple LLM providers (Gemini, DeepSeek), skill-based architecture, conversation persistence, and Telegram integration.

## 📋 Overview

The Hercules Agent Framework provides a clean, modular architecture for building AI agents that can:
- Work with multiple LLM providers (Gemini, DeepSeek)
- Persist conversations and messages using SQLite
- Execute skills based on user intents
- Integrate with Telegram for messaging
- Be easily extended with new skills and providers

## 📦 Installation

Since this framework uses only Python standard library modules, no external dependencies are required:

```bash
# Clone the repository
git clone https://github.com/yourusername/hercules-agent.git
cd hercules-agent

# The framework is ready to use - no installation needed
```

## 📁 Project Structure

```
hercules_agent/
├── hercules_agent/                 # Main package
│   ├── __init__.py
│   ├── core/                       # Core components
│   │   ├── __init__.py
│   │   ├── llm_provider.py         # LLM provider interfaces
│   │   ├── agent_controller.py     # Main agent logic
│   │   └── telegram_handler.py     # Telegram integration
│   ├── skills/                     # Skill management
│   │   ├── __init__.py
│   │   └── manager.py              # Skill registration and execution
│   └── utils/                      # Utility components
│       ├── __init__.py
│       └── memory_manager.py       # SQLite persistence
├── cidog_framework.py              # Backward compatibility layer
├── requirements.txt                # No external dependencies
└── .gitignore                      # Git ignore rules
```

## 🚀 Quick Start

Here's a basic example of how to use the framework:

```python
import asyncio
from hercules_agent.core.llm_provider import LLMProvider
from hercules_agent.core.agent_controller import AgentController
from hercules_agent.skills.manager import Skill
from hercules_agent.utils.memory_manager import MemoryManager

# Initialize components
memory_manager = MemoryManager("./data/agent.db")
agent_controller = AgentController(
    telegram_allowed_user_ids=["123456789"],  # Replace with allowed user IDs
    default_llm_provider=LLMProvider.GEMINI
)

# Configure LLM providers (add your API keys)
agent_controller.configure_provider(LLMProvider.GEMINI, "your_gemini_api_key")
agent_controller.configure_provider(LLMProvider.DEEPSEEK, "your_deepseek_api_key")

# Process a message
async def main():
    response = await agent_controller.process_message(
        user_id="123456789",
        conversation_id="conv_001",
        message_text="Hello, how are you?"
    )
    print(response)

# Run the example
asyncio.run(main())
```

## 🔧 Components

### LLM Providers
Supports multiple LLM providers through a common interface:
- Gemini (Google)
- DeepSeek

### Skill System
- Skills are pluggable components that can handle specific intents
- Easy to create and register new skills
- Skill manager handles routing intents to appropriate skills

### Memory Management
- SQLite-based persistence for conversations and messages
- Automatic conversation history retrieval
- Efficient message storage and retrieval

### Telegram Integration
- Placeholder for Telegram bot integration
- Easy to extend with actual Telegram client libraries

## 🔄 Backward Compatibility

The original `cidog_framework.py` file has been maintained as a backward compatibility layer. All existing code that imports from `cidog_framework` will continue to work without modification.

## 📝 License

This project is open source and available for use and modification.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

**Note**: This framework is designed to be extensible and easy to understand. Each component has a single responsibility, making it simple to maintain and extend.