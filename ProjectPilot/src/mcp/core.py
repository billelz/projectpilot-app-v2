import subprocess
import json
import shutil
from pathlib import Path

MAX_TOOL_RESULT_CHARS = 1500   # hard cap per tool result
MAX_HISTORY_MESSAGES = 6        # keep only the last N messages (sliding window)


class MCPClient:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.process = None
        # The MCP filesystem server runs through ``npx`` (Node.js). Most end
        # users — and confined/packaged environments — don't ship Node, so we
        # fall back to reading files natively when it isn't available.
        if shutil.which("npx"):
            try:
                self.process = subprocess.Popen(
                    ["npx", "-y", "@modelcontextprotocol/server-filesystem", project_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            except Exception as e:
                print(f"[MCP] Failed to start npx filesystem server, using native fallback: {e}")
                self.process = None

    def send(self, payload: dict):
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def receive(self):
        while True:
            line = self.process.stdout.readline()
            if line.strip():
                return json.loads(line)

    def _native_read_file(self, arguments: dict) -> dict:
        """Read a file directly, mirroring the MCP server response shape."""
        path = arguments.get("path", "")
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"result": {"content": [{"text": f"Error reading file: {e}"}]}}
        return {"result": {"content": [{"text": text}]}}

    def call_tool(self, name: str, arguments: dict):
        if self.process is None:
            # Native fallback: only read_file is supported (matches run_agent).
            if name == "read_file":
                return self._native_read_file(arguments)
            return {"result": {"content": [{"text": f"Error: tool '{name}' not available."}]}}
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }
        self.send(request)
        return self.receive()

    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def init(self):
        if self.process is None:
            return
        self.send({
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "projectpilot", "version": "1.0"}
            }
        })
        self.receive()  # consume the initialize response
        # MCP requires sending "initialized" notification after init response
        self.send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        })


# Only allow read_file, and only on a pre-approved list of paths.
# This is set per-call by general_install_guide, not hardcoded.
TOOLS_TEMPLATE = """
You are an AI agent with access to ONE tool: read_file.

ALLOWED FILES (you may ONLY read these — nothing else exists to you):
{allowed_files}

To read a file, respond ONLY with JSON:
{{"tool": "read_file", "arguments": {{"path": "<one of the allowed files above>"}}}}

When you have enough information, respond ONLY with JSON:
{{"final": "your answer"}}

Do not call read_file more than once per file. Do not ask for files not in the list.
"""


def run_agent(llm_client, mcp_client, user_input: str, allowed_files: list[str]):
    system_prompt = TOOLS_TEMPLATE.format(allowed_files="\n".join(f"- {f}" for f in allowed_files))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    already_read = set()

    for _ in range(6):  # fewer iterations needed now
            response = llm_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.2
            )
            content = response.choices[0].message.content
            print(f"[LLM RAW OUTPUT]: {content!r}")

            try:
                data = json.loads(content)
            except Exception:
                return f"Invalid LLM output: {content}"

            if "tool" in data:
                tool_name = data["tool"]
                args = data.get("arguments", {})
                path = args.get("path", "")

                # Enforce allowlist
                if tool_name != "read_file" or path not in allowed_files:
                    tool_text = "Error: file not allowed or tool not available."
                elif path in already_read:
                    tool_text = "Error: already read this file."
                else:
                    tool_result = mcp_client.call_tool(tool_name, args)
                    raw = tool_result.get("result", {}).get("content", [])
                    tool_text = raw[0].get("text", "") if raw else str(tool_result)
                    tool_text = tool_text[:MAX_TOOL_RESULT_CHARS]  # hard cap
                    already_read.add(path)

                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Tool result:\n{tool_text}"})

                # Sliding window: keep system + user goal + last N exchanges
                if len(messages) > MAX_HISTORY_MESSAGES:
                    messages = [messages[0], messages[1]] + messages[-(MAX_HISTORY_MESSAGES - 2):]

            elif "final" in data:
                return data["final"]

            else:
                # Model returned a final-shaped JSON directly (e.g. {"commands": [...]})
                return data

    return "Agent stopped (too many steps)"