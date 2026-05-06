"""
Built-in tool schemas and executor for Hercules Agent.

Tools (16 total):
  shell, read_file, write_file, patch_file, diff,
  list_dir, glob, grep, python_exec,
  web_search, http_get, http_post,
  memo_write, memo_read,
  todo_write, todo_read
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_MEMO_PATH = os.path.expanduser("~/.hercules_memo.md")

logger = logging.getLogger(__name__)

# ── Session-scoped todo list (persisted in memory during a session) ────────────
_TODO_LIST: List[Dict[str, Any]] = []


# ── Tool schema definitions ────────────────────────────────────────────────────

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": (
                "Execute a shell command. Use for: running tests, git, pip/npm installs, "
                "grepping file trees, reading process output, system info, anything that "
                "needs a terminal. Output is truncated to 8 000 chars."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run."},
                    "cwd": {"type": "string", "description": "Working directory (optional)."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file and return its text content. "
                "Use offset/limit to read only part of a large file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read."},
                    "offset": {"type": "integer", "description": "Start line (1-indexed, optional)."},
                    "limit": {"type": "integer", "description": "Max lines to return (optional)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write (create or overwrite) a file. "
                "For targeted edits to existing files, prefer patch_file instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                    "content": {"type": "string", "description": "Full file content."},
                    "mode": {"type": "string", "enum": ["w", "a"], "description": "'w'=overwrite (default), 'a'=append."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": (
                "Surgically replace one exact string in a file with another. "
                "The old_str must match the file exactly (including whitespace/indentation). "
                "Replaces only the first occurrence. "
                "Always read the file first to get the exact text. "
                "Returns a unified diff of what changed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "old_str": {"type": "string", "description": "Exact string to find and replace."},
                    "new_str": {"type": "string", "description": "Replacement string."},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diff",
            "description": (
                "Show a unified diff between two files, or between a file and new proposed content. "
                "Use to preview changes before applying them, or to compare any two text sources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path_a":    {"type": "string", "description": "First file path (required)."},
                    "path_b":    {"type": "string", "description": "Second file path (optional — use instead of content_b)."},
                    "content_b": {"type": "string", "description": "New content string to diff against path_a (optional — use instead of path_b)."},
                    "context":   {"type": "integer", "description": "Lines of context around changes (default 3)."},
                },
                "required": ["path_a"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default '.')."},
                    "pattern": {"type": "string", "description": "Regex filter for names (optional)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": (
                "Find files matching a glob pattern (e.g. '**/*.py', 'src/**/*.ts', '*.json'). "
                "Faster than shell find for discovering files by name. "
                "Returns a sorted list of matching paths relative to root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string",  "description": "Glob pattern (e.g. '**/*.py')."},
                    "root":    {"type": "string",  "description": "Root directory to search from (default '.')."},
                    "limit":   {"type": "integer", "description": "Max results to return (default 100)."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "Search files for a regex pattern. Returns matching lines with file names and "
                "line numbers. Use file_pattern to restrict search (e.g. '*.py')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for."},
                    "path": {"type": "string", "description": "File or directory to search (default '.')."},
                    "file_pattern": {"type": "string", "description": "Glob pattern for file filter (e.g. '*.py')."},
                    "context_lines": {"type": "integer", "description": "Lines of context around matches (default 2)."},
                    "case_insensitive": {"type": "boolean", "description": "Case-insensitive search (default false)."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python_exec",
            "description": (
                "Execute Python code and return stdout/stderr. "
                "Set sandbox=false for full stdlib access (needed for file I/O, subprocess, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                    "sandbox": {"type": "boolean", "description": "Restrict builtins (default true)."},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo. Returns titles, URLs, and snippets. "
                "Best for finding docs, packages, or recent information. "
                "Set fetch_content=true to also retrieve the full text of the top result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query":         {"type": "string",  "description": "Search query."},
                    "limit":         {"type": "integer", "description": "Max results (default 6)."},
                    "fetch_content": {"type": "boolean", "description": "Fetch full text of top result (default false)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "Fetch a URL via HTTP GET and return the response body (max 8 000 chars).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":     {"type": "string",  "description": "URL to fetch."},
                    "headers": {"type": "object",  "description": "Optional request headers."},
                    "timeout": {"type": "integer", "description": "Timeout seconds (default 30)."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_post",
            "description": (
                "Send an HTTP request with a body (POST, PUT, PATCH, DELETE). "
                "Use for REST API calls, webhooks, or any write operation. "
                "Returns status code and response body."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url":     {"type": "string",  "description": "URL to call."},
                    "method":  {"type": "string",  "enum": ["POST", "PUT", "PATCH", "DELETE"], "description": "HTTP method (default POST)."},
                    "body":    {"type": "object",  "description": "JSON body to send (optional)."},
                    "data":    {"type": "string",  "description": "Raw string body (optional, use instead of body)."},
                    "headers": {"type": "object",  "description": "Request headers (optional)."},
                    "timeout": {"type": "integer", "description": "Timeout seconds (default 30)."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memo_write",
            "description": (
                "Write a persistent note to your cross-session memory file (~/.hercules_memo.md). "
                "Use this to remember important facts, preferences, project context, or credentials hints "
                "that should survive across sessions. Content is appended with a timestamp header."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string",  "description": "Markdown content to store."},
                    "heading": {"type": "string",  "description": "Short heading/title for this memo entry (optional)."},
                    "replace": {"type": "boolean", "description": "If true, overwrite all existing memo content (default false)."},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memo_read",
            "description": (
                "Read your persistent cross-session memory file (~/.hercules_memo.md). "
                "Call this at the start of a session or when you need to recall stored facts."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_write",
            "description": (
                "Create or replace the session task list. "
                "Use this at the start of any multi-step task to plan your work, "
                "and call it again to update item statuses. "
                "Each item has: id (int), content (str), status ('pending'|'in_progress'|'done')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "Array of todo items.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id":      {"type": "integer"},
                                "content": {"type": "string"},
                                "status":  {"type": "string", "enum": ["pending", "in_progress", "done"]},
                            },
                            "required": ["id", "content", "status"],
                        },
                    }
                },
                "required": ["todos"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_read",
            "description": "Read the current session task list.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ── Main dispatcher ────────────────────────────────────────────────────────────

async def execute_tool(name: str, args: Dict[str, Any]) -> str:
    try:
        dispatch = {
            "shell":       _shell,
            "read_file":   _read_file,
            "write_file":  _write_file,
            "patch_file":  _patch_file,
            "diff":        _diff,
            "list_dir":    _list_dir,
            "glob":        _glob,
            "grep":        _grep,
            "python_exec": _python_exec,
            "web_search":  _web_search,
            "http_get":    _http_get,
            "http_post":   _http_post,
            "memo_write":  _memo_write,
            "memo_read":   _memo_read,
            "todo_write":  _todo_write,
            "todo_read":   _todo_read,
        }
        fn = dispatch.get(name)
        if fn is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        return await fn(args)
    except Exception as exc:
        logger.exception(f"Tool {name} raised: {exc}")
        return json.dumps({"error": str(exc)})


# ── Tool implementations ───────────────────────────────────────────────────────

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
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return json.dumps({"error": f"Command timed out after {timeout}s", "command": command})

        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        rc = proc.returncode

        MAX = 8000
        if len(out) > MAX:
            out = out[:MAX] + f"\n… [{len(out) - MAX} chars truncated]"
        if len(err) > MAX:
            err = err[:MAX] + f"\n… [{len(err) - MAX} chars truncated]"

        result: Dict[str, Any] = {"returncode": rc}
        if out.strip():
            result["stdout"] = out
        if err.strip():
            result["stderr"] = err
        if rc != 0 and not out.strip() and not err.strip():
            result["note"] = "Command produced no output and exited non-zero"
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)})


async def _read_file(args: Dict[str, Any]) -> str:
    path = os.path.expanduser(args["path"])
    offset = int(args.get("offset") or 0)
    limit = args.get("limit")

    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        if offset > 0:
            lines = lines[offset - 1:]
        if limit is not None:
            lines = lines[:int(limit)]
        content = "".join(lines)
        MAX = 12000
        note = ""
        if len(content) > MAX:
            content = content[:MAX]
            note = f"\n\n[File truncated — showed first {MAX} chars of {total} lines total. Use offset/limit to read more.]"
        return content + note if content else "(empty file)"
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
        lines = content.count("\n") + 1
        return json.dumps({"success": True, "path": path, "bytes_written": len(content.encode()), "lines": lines})
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
            # Find close matches to help the model
            lines = content.split("\n")
            old_lines = old_str.split("\n")
            hint = ""
            if old_lines:
                first = old_lines[0].strip()
                for i, line in enumerate(lines):
                    if first and first[:20] in line:
                        hint = f"\nNearby line {i+1}: {line!r}"
                        break
            return json.dumps({
                "error": "old_str not found in file. Check exact whitespace and indentation.",
                "tip": "Use read_file first to get the exact text." + hint,
            })
        new_content = content.replace(old_str, new_str, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Return a unified diff of exactly what changed
        udiff = "".join(difflib.unified_diff(
            old_str.splitlines(keepends=True),
            new_str.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(path)}",
            tofile=f"b/{os.path.basename(path)}",
            n=2,
        ))
        return json.dumps({
            "success": True,
            "path": path,
            "diff": udiff or "(content identical — no visible change)",
        })
    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {path}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _list_dir(args: Dict[str, Any]) -> str:
    path = os.path.expanduser(args.get("path") or ".")
    pattern = args.get("pattern")
    try:
        import re
        entries = []
        for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
            if pattern and not re.search(pattern, entry.name):
                continue
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return json.dumps(entries, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({"error": f"Directory not found: {path}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _grep(args: Dict[str, Any]) -> str:
    pattern = args["pattern"]
    search_path = args.get("path", ".")
    file_pattern = args.get("file_pattern", "*")
    context_lines = int(args.get("context_lines", 2))
    case_insensitive = args.get("case_insensitive", False)

    try:
        cmd = ["grep", "-rn", "--include", file_pattern, f"-C{context_lines}"]
        if case_insensitive:
            cmd.append("-i")
        cmd += [pattern, search_path]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        out = stdout.decode(errors="replace")

        if proc.returncode == 1 and not out.strip():
            return f"No matches found for pattern: {pattern!r}"

        if len(out) > 8000:
            out = out[:8000] + "\n… [truncated]"

        return out if out.strip() else stderr.decode(errors="replace")
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _python_exec(args: Dict[str, Any]) -> str:
    code = args["code"]
    sandbox = bool(args.get("sandbox", True))
    try:
        from ..interpreter.code_interpreter import CodeInterpreter, InterpreterConfig
        config = InterpreterConfig(enable_sandbox=sandbox, timeout=30)
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
            out["return_value"] = str(result.return_value)
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _web_search(args: Dict[str, Any]) -> str:
    query         = args["query"]
    limit         = int(args.get("limit", 6))
    fetch_content = bool(args.get("fetch_content", False))

    try:
        import aiohttp
        import urllib.parse
        import re

        encoded = urllib.parse.quote_plus(query)
        results = []

        # Attempt 1: DuckDuckGo Instant Answer API (JSON)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10),
                                   headers={"User-Agent": "HerculesAgent/1.0"}) as resp:
                data = await resp.json(content_type=None)

        if data.get("Abstract"):
            results.append({
                "title":   data.get("Heading", "Answer"),
                "url":     data.get("AbstractURL", ""),
                "snippet": data["Abstract"],
                "source":  data.get("AbstractSource", ""),
            })
        for item in data.get("RelatedTopics", []):
            if len(results) >= limit:
                break
            if isinstance(item, dict) and item.get("Text"):
                results.append({"title": item["Text"][:100], "url": item.get("FirstURL", ""), "snippet": item["Text"]})
            elif isinstance(item, dict) and item.get("Topics"):
                for sub in item["Topics"]:
                    if len(results) >= limit:
                        break
                    if isinstance(sub, dict) and sub.get("Text"):
                        results.append({"title": sub["Text"][:100], "url": sub.get("FirstURL", ""), "snippet": sub["Text"]})

        # Attempt 2: DuckDuckGo lite HTML scraper
        if not results:
            lite_url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
            async with aiohttp.ClientSession() as session:
                async with session.get(lite_url, timeout=aiohttp.ClientTimeout(total=12),
                                       headers={"User-Agent": "Mozilla/5.0 (compatible; HerculesAgent/1.0)"}) as resp:
                    html = await resp.text(errors="replace")
            link_pat    = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
            snippet_pat = re.compile(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL)
            links    = link_pat.findall(html)
            snippets = [re.sub(r'<[^>]+>', '', s) for s in snippet_pat.findall(html)]
            for i, (u, title) in enumerate(links[:limit]):
                results.append({"title": title.strip(), "url": u, "snippet": snippets[i].strip() if i < len(snippets) else ""})

        if not results:
            return json.dumps({"note": "No results found. Try a different query.", "query": query})

        # Optionally fetch full text of the top result
        if fetch_content and results:
            top_url = results[0].get("url", "")
            if top_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(top_url, timeout=aiohttp.ClientTimeout(total=15),
                                               headers={"User-Agent": "Mozilla/5.0 (compatible; HerculesAgent/1.0)"}) as resp:
                            raw = await resp.text(errors="replace")
                    text = re.sub(r'<[^>]+>', ' ', raw)
                    text = re.sub(r'\s+', ' ', text).strip()
                    results[0]["full_content"] = text[:4000] + ("…" if len(text) > 4000 else "")
                except Exception:
                    pass

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
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                status = resp.status
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct:
                    body = json.dumps(await resp.json(content_type=None), indent=2)
                else:
                    body = await resp.text(errors="replace")
        MAX = 8000
        if len(body) > MAX:
            body = body[:MAX] + "\n… [truncated]"
        return json.dumps({"status": status, "content_type": ct, "body": body})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _diff(args: Dict[str, Any]) -> str:
    path_a    = os.path.expanduser(args["path_a"])
    path_b    = args.get("path_b")
    content_b = args.get("content_b")
    context   = int(args.get("context", 3))
    try:
        with open(path_a, "r", encoding="utf-8", errors="replace") as f:
            lines_a = f.readlines()
        if path_b:
            path_b_exp = os.path.expanduser(path_b)
            with open(path_b_exp, "r", encoding="utf-8", errors="replace") as f:
                lines_b = f.readlines()
            label_b = path_b_exp
        elif content_b is not None:
            lines_b = content_b.splitlines(keepends=True)
            label_b = f"{path_a} (proposed)"
        else:
            return json.dumps({"error": "Provide either path_b or content_b."})
        udiff = "".join(difflib.unified_diff(lines_a, lines_b, fromfile=path_a, tofile=label_b, n=context))
        if not udiff:
            return json.dumps({"result": "Files are identical — no differences found."})
        if len(udiff) > 8000:
            udiff = udiff[:8000] + "\n… [diff truncated]"
        return udiff
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _glob(args: Dict[str, Any]) -> str:
    pattern = args["pattern"]
    root    = args.get("root", ".")
    limit   = int(args.get("limit", 100))
    try:
        root_path = Path(os.path.expanduser(root)).resolve()
        all_matches = sorted(root_path.glob(pattern))
        # Skip hidden dirs unless explicitly targeted
        if not pattern.startswith("."):
            all_matches = [
                p for p in all_matches
                if not any(part.startswith(".") for part in p.parts[len(root_path.parts):])
            ]
        paths = [str(p.relative_to(root_path)) for p in all_matches[:limit]]
        result: Dict[str, Any] = {"matches": paths, "count": len(paths)}
        if len(all_matches) > limit:
            result["note"] = f"{len(all_matches) - limit} more results omitted (increase limit)"
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _http_post(args: Dict[str, Any]) -> str:
    url     = args["url"]
    method  = args.get("method", "POST").upper()
    body    = args.get("body")
    data    = args.get("data")
    headers = dict(args.get("headers") or {})
    timeout = int(args.get("timeout", 30))
    try:
        import aiohttp
        if body is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        async with aiohttp.ClientSession() as session:
            req_kwargs: Dict[str, Any] = {
                "headers": headers,
                "timeout": aiohttp.ClientTimeout(total=timeout),
            }
            if body is not None:
                req_kwargs["json"] = body
            elif data is not None:
                req_kwargs["data"] = data
            async with session.request(method, url, **req_kwargs) as resp:
                status = resp.status
                ct     = resp.headers.get("Content-Type", "")
                try:
                    resp_body = json.dumps(await resp.json(content_type=None), indent=2) if "json" in ct else await resp.text(errors="replace")
                except Exception:
                    resp_body = "(could not decode response)"
        if len(resp_body) > 8000:
            resp_body = resp_body[:8000] + "\n… [truncated]"
        return json.dumps({"status": status, "method": method, "content_type": ct, "body": resp_body})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _memo_write(args: Dict[str, Any]) -> str:
    content = args["content"]
    heading = args.get("heading", "")
    replace = bool(args.get("replace", False))
    try:
        from datetime import datetime
        ts    = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        title = f"## {heading}" if heading else "## Note"
        entry = f"\n{title}\n_Saved: {ts}_\n\n{content}\n\n---\n"
        if replace:
            with open(_MEMO_PATH, "w", encoding="utf-8") as f:
                f.write(f"# Hercules Memory\n{entry}")
        else:
            with open(_MEMO_PATH, "a", encoding="utf-8") as f:
                if not os.path.exists(_MEMO_PATH):
                    f.write("# Hercules Memory\n")
                f.write(entry)
        size = os.path.getsize(_MEMO_PATH)
        return json.dumps({"success": True, "memo_path": _MEMO_PATH, "size_bytes": size})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _memo_read(args: Dict[str, Any]) -> str:
    try:
        if not os.path.exists(_MEMO_PATH):
            return json.dumps({"content": "(empty — no memo entries yet)", "memo_path": _MEMO_PATH})
        with open(_MEMO_PATH, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 8000:
            content = content[:8000] + "\n… [memo truncated]"
        return json.dumps({"content": content, "memo_path": _MEMO_PATH})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _todo_write(args: Dict[str, Any]) -> str:
    global _TODO_LIST
    todos = args.get("todos", [])
    _TODO_LIST = todos
    pending = sum(1 for t in todos if t.get("status") == "pending")
    in_prog = sum(1 for t in todos if t.get("status") == "in_progress")
    done = sum(1 for t in todos if t.get("status") == "done")
    return json.dumps({
        "success": True,
        "total": len(todos),
        "pending": pending,
        "in_progress": in_prog,
        "done": done,
    })


async def _todo_read(args: Dict[str, Any]) -> str:
    if not _TODO_LIST:
        return json.dumps({"todos": [], "note": "No todos set for this session."})
    return json.dumps({"todos": _TODO_LIST})


def get_todos() -> List[Dict[str, Any]]:
    """Expose current todos to the UI."""
    return list(_TODO_LIST)
