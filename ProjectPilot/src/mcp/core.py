import subprocess
import json

class MCPClient:
    def __init__(self, project_path: str):
        self.project_path = project_path

        self.process = subprocess.Popen(
            [
                "npx",
                "-y",
                "@modelcontextprotocol/server-filesystem",
                project_path
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
  
    def send(self, payload: dict):
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
    def receive(self):
        while True:
            line = self.process.stdout.readline()
            if line.strip():
                return json.loads(line)
    def call_tool(self, name: str, arguments: dict):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        }

        self.send(request)
        return self.receive()
    def is_alive(self):
        return self.process.poll() is None
    def init(self):
        init_msg = {
            "method": "initialize",
            "params": {}
        }

        self.send(init_msg)
TOOLS = """
        You are an AI agent with access to tools.

        TOOLS AVAILABLE:
        - read_file: {"path": "..."}
        - list_directory: {"path": "..."}

        RULES:
        If you need a tool, respond ONLY in JSON:

        {
        "tool": "tool_name",
        "arguments": {}
        }

        If you are done, respond:

        {
        "final": "your answer"
        }
        """
def run_agent(llm_client, mcp_client, user_input: str):
        messages = [
            {"role": "system", "content": TOOLS},
            {"role": "user", "content": user_input}
        ]
        for _ in range(12):  
            response = llm_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.2
            )
            content = response.choices[0].message.content
            print("\n[LLM]\n", content)
            try:
                data = json.loads(content)
            except Exception:
                return f"Invalid LLM output: {content}"
            if "tool" in data:
                tool_name = data["tool"]
                args = data.get("arguments", {})
                print(f"\n[TOOL CALL] {tool_name} {args}")
                tool_result = mcp_client.call_tool(tool_name, args)
                tool_text = tool_result.get("result", {}).get("content", [])
                if tool_text:
                    tool_text = tool_text[0].get("text", "")
                else:
                    tool_text = str(tool_result)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Tool result:\n{tool_text}"})
            elif "final" in data:
                return data["final"]
        return "Agent stopped (too many steps)"