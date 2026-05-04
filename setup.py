#!/usr/bin/env python3
"""
Hercules Agent - Setup script
"""
from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# Read version from package
version = "2.0.0"

setup(
    name="hercules-agent",
    version=version,
    author="Hercules Agent Team",
    description="Multi-platform AI agent with LLM abstraction, skill system, and MCP support",
    long_description=(here / "README.md").read_text() if (here / "README.md").exists() else "",
    long_description_content_type="text/markdown",
    url="https://github.com/Sldark23/Hercules-agent",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.9.0",
        "pydantic>=2.5.0",
        "python-dotenv>=1.0.0",
        "litellm>=1.40.0",
        "python-telegram-bot>=20.0",
        "discord.py>=2.3.0",
        "slack-sdk>=3.21.0",
        "aiosqlite>=0.19.0",
        "httpx>=0.25.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "hercules=hercules_agent.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "hercules_agent": ["py.typed"],
    },
)