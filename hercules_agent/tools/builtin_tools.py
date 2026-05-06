"""
Built-in tool schemas and executor for Hercules Agent.

Provides the full OpenAI function-calling schema for all built-in tools and
a single async `execute_tool(name, args)` coroutine that dispatches to the
right handler — ToolRegistry, CodeInterpreter, or direct aiohttp.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Tool schema definitions ────────────────────────────────────────────────────

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": (
                "Execute a shell command in the current working directory. "
                "Use for running scripts, git commands, installing packages, "
                "compiling code, reading system state, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (optional, defaults to project root).",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 60).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from disk and return its contents as text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path."},
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed, optional).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to return (optional).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (or overwrite) a file on disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write."},
                    "content": {"type": "string", "description": "Full content to write."},
                    "mode": {
                        "type": "string",
                        "enum": ["w", "a"],
                        "description": "'w' to overwrite (default), 'a' to append.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (defaults to '.').",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional regex pattern to filter entries.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo and return a list of results "
                "(title, URL, snippet). Best for finding current information, "
                "documentation, or news."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "Fetch a URL via HTTP GET and return the response body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch."},
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30).",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python_exec",
            "description": (
                "Execute Python code and return stdout/stderr. "
                "Useful for calculations, data processing, prototyping, and "
                "running code that doesn't need file system access."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                    "sandbox": {
                        "type": "boolean",
                        "description": "Run in sandbox (default True). Set False for full access.",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": (
                "Apply an exact string replacement to a file. "
                "Replaces the first occurrence of `old_str` with `new_str`. "
                "Use this for targeted edits instead of rewriting whole files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "old_str": {
                        "type": "string",
                        "description": "Exact string to find (including whitespace/indentation).",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "String to replace it with.",
                    },
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for a pattern in files using grep-like functionality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for."},
                    "path": {
                        "type": "string",
                        "description": "File or directory to search (default '.').",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g. '*.py').",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context around each match (default 2).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]


# ── Tool executor ──────────────────────────────────────────────────────────────

async def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """Dispatch a tool call and return the result as a string."""
    try:
        if name == "shell":
            return await _shell(args)
        elif name == "read_file":
            return await _read_file(args)
        elif name == "write_file":
            return await _write_file(args)
        elif name == "list_dir":
            return await _list_dir(args)
        elif name == "web_search":
            return await _web_search(args)
        elif name == "http_get":
            return await _http_get(args)
        elif name == "python_exec":
            return await _python_exec(args)
        elif name == "patch_file":
            return await _patch_file(args)
        elif name == "grep":
            return await _grep(args)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        logger.exception(f"Tool {name} raised: {exc}")
        return json.dumps({"error": str(exc)})


# ── Individual tool implementations ───────────────────────────────────────────

async def _shell(args: Dict[str, Any]) -> str:
    command = args["command"]
    cwd = args.get("cwd") or os.getcwd()
    timeout = int(args.get("timeout", 60))

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        rc = proc.returncode

        # Truncate very long output
        max_chars = 8000
        if len(out) > max_chars:
            out = out[:max_chars] + f"\n... [truncated {len(out) - max_chars} chars]"
        if len(err) > max_chars:
            err = err[:max_chars] + f"\n... [truncated {len(err) - max_chars} chars]"

        result: Dict[str, Any] = {"returncode": rc}
        if out:
            result["stdout"] = out
        if err:
            result["stderr"] = err
        if rc != 0 and not out and not err:
            result["note"] = "Command produced no output"
        return json.dumps(result, ensure_ascii=False)

    except asyncio.TimeoutError:
        return json.dumps({"error": f"Command timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _read_file(args: Dict[str, Any]) -> str:
    path = os.path.expanduser(args["path"])
    offset = int(args.get("offset", 0) or 0)
    limit = args.get("limit")

    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()

        if offset > 0:
            lines = lines[offset - 1:]
        if limit is not None:
            lines = lines[:int(limit)]

        content = "".join(lines)
        if len(content) > 10000:
            content = content[:10000] + f"\n... [truncated]"
        return content if content else "(empty file)"
    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {path}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _write_file(args: Dict[str, Any]) -> str:
    path = os.path.expanduser(args["path"])
    content = args["content"]
    mode = args.get("mode", "w")

    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)
        return json.dumps({"success": True, "path": path, "bytes": len(content.encode())})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _list_dir(args: Dict[str, Any]) -> str:
    path = os.path.expanduser(args.get("path") or ".")
    pattern = args.get("pattern")

    try:
        import re
        entries = []
        for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name)):
            if pattern and not re.search(pattern, entry.name):
                continue
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return json.dumps(entries, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _web_search(args: Dict[str, Any]) -> str:
    query = args["query"]
    limit = int(args.get("limit", 5))

    try:
        import aiohttp, urllib.parse
        encoded = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)

        results = []

        # Abstract / instant answer
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", "DuckDuckGo Answer"),
                "url": data.get("AbstractURL", ""),
                "snippet": data["Abstract"],
            })

        # Related topics
        for item in data.get("RelatedTopics", []):
            if len(results) >= limit:
                break
            if isinstance(item, dict) and item.get("Text"):
                results.append({
                    "title": item.get("Text", "")[:80],
                    "url": item.get("FirstURL", ""),
                    "snippet": item.get("Text", ""),
                })

        if not results:
            return json.dumps({
                "note": "No results from DuckDuckGo instant API. Try a more specific query.",
                "query": query,
            })

        return json.dumps(results[:limit], ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e), "query": query})


async def _http_get(args: Dict[str, Any]) -> str:
    url = args["url"]
    headers = args.get("headers") or {}
    timeout = int(args.get("timeout", 30))

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                status = resp.status
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct:
                    body = json.dumps(await resp.json(content_type=None))
                else:
                    body = await resp.text(errors="replace")

        max_chars = 8000
        if len(body) > max_chars:
            body = body[:max_chars] + "\n... [truncated]"

        return json.dumps({"status": status, "body": body})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _python_exec(args: Dict[str, Any]) -> str:
    code = args["code"]
    sandbox = args.get("sandbox", True)

    try:
        from ..interpreter.code_interpreter import CodeInterpreter, InterpreterConfig
        config = InterpreterConfig(enable_sandbox=bool(sandbox), timeout=30)
        interpreter = CodeInterpreter(config)
        result = await interpreter.execute(code, language="python")

        out: Dict[str, Any] = {"success": result.success}
        if result.stdout:
            out["stdout"] = result.stdout
        if result.stderr:
            out["stderr"] = result.stderr
        if result.error:
            out["error"] = result.error
        if result.return_value:
            out["return_value"] = result.return_value
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _patch_file(args: Dict[str, Any]) -> str:
    path = os.path.expanduser(args["path"])
    old_str = args["old_str"]
    new_str = args["new_str"]

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        if old_str not in content:
            return json.dumps({"error": f"old_str not found in {path}. Check exact whitespace/indentation."})

        new_content = content.replace(old_str, new_str, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return json.dumps({"success": True, "path": path})
    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {path}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _grep(args: Dict[str, Any]) -> str:
    pattern = args["pattern"]
    search_path = args.get("path", ".")
    file_pattern = args.get("file_pattern", "*")
    context_lines = int(args.get("context_lines", 2))

    try:
        import subprocess
        cmd = ["grep", "-rn", "--include", file_pattern, f"-C{context_lines}", pattern, search_path]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")

        if len(out) > 8000:
            out = out[:8000] + "\n... [truncated]"

        if proc.returncode == 1 and not out:
            return json.dumps({"matches": 0, "note": "No matches found."})

        return out if out else json.dumps({"stderr": err})
    except Exception as e:
        return json.dumps({"error": str(e)})
