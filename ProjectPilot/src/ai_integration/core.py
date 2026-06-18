import os
import sys
from pathlib import Path
from groq import Groq
from project_analyzer.models import ProjectInfo
from .utils import get_system_info,safe_parse_ai_json, detect_compose_command,docker_exists,order_compose_files,extract_ports_from_compose,extract_ports_from_dockerfile,order_dockerfiles
from typing import Dict, Any, List, Optional
from mcp.core import run_agent
from dotenv import load_dotenv


def _load_environment() -> None:
    """Load environment variables, including a .env bundled by PyInstaller.

    When the backend is frozen into a single binary, PyInstaller extracts
    bundled data files into ``sys._MEIPASS``. The CI build writes the Groq
    API key into a ``.env`` there, so we must load it explicitly. In
    development we also load any local ``.env`` from the working directory.
    """
    if getattr(sys, "frozen", False):
        bundled_env = Path(getattr(sys, "_MEIPASS", "")) / ".env"
        if bundled_env.exists():
            load_dotenv(bundled_env)
    load_dotenv()


_load_environment()

# The Groq client is created lazily so that a missing API key never crashes
# the backend at import time (which would make the whole app "unreachable").
_client: Optional[Groq] = None


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. AI-powered features are unavailable."
            )
        _client = Groq(api_key=api_key)
    return _client


user_os = get_system_info()
def readme_install_guide(info: ProjectInfo,mcp_client) -> Dict[str, Any]:
    user_input = f"""
You are a README installation agent.

Your ONLY job is to extract setup and run commands
from the README documentation.

Project path: {info.path}
User OS: {user_os}

Rules:
- Start by reading the README
- ONLY use information explicitly written in the README
- DO NOT inspect Dockerfiles
- DO NOT inspect package.json
- DO NOT infer alternative methods
- DO NOT guess missing steps
- Return ONLY the commands mentioned in the README

Return format:
{{
  "commands": ["command1", "command2"]
}}

"""
    result = run_agent(
        llm_client=get_client(),
        mcp_client=mcp_client,
        user_input=user_input
    )

    return result
def docker_check() -> dict:
    if docker_exists():
        return {
            "status": "ok",
            "docker": True
        }

    prompt = f"""
You are a system installer assistant.

User OS: {user_os}

Task:
Generate Docker installation instructions.

IMPORTANT:
Return ONLY a JSON LIST of strings.

Each item must be a copy-paste command or note.

Example:
[
  "sudo apt update",
  "sudo apt install docker.io",
  "sudo systemctl start docker"
]

Rules:
- NO objects
- NO keys like tool/commands
- ONLY a list of strings
- Commands must be executable
"""

    response = get_client().chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    raw = response.choices[0].message.content

    return {
        "status": "ai_generated",
        "commands": safe_parse_ai_json(raw, []),
        "raw_output": raw
    }
def select_compose_files(valid_files: List[str]) -> List[str]:
    base = []
    override = []
    variants = []
    for f in valid_files:
        name = Path(f).name.lower()
        if name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            base.append(f)
        elif "override" in name:
            override.append(f)
        else:
            variants.append(f)
    if base:
        return base + override
    if variants:
        return [variants[0]]  
    return [valid_files[0]]
def docker_compose_install(info: ProjectInfo,mcp_client) -> Dict[str, Any]:
    all_files: List[str] = info.docker_path
    if not all_files:
        return {
            "type": "docker-compose",
            "error": "No docker-related files provided"
        }
    compose_files = [
        f for f in all_files
        if "compose" in Path(f).name.lower()
    ]
    valid_files = [f for f in compose_files if Path(f).exists()]
    if not valid_files:
        return dockerfile_install_agent(info)
    selected_files = select_compose_files(valid_files)
    selected_files = order_compose_files(selected_files)
    compose_cmd = detect_compose_command()
    selected_files = [str(Path(f).resolve()) for f in selected_files]
    working_dir = str(Path(selected_files[0]).parent)
    file_flags = " ".join([f'-f "{f}"' for f in selected_files])
    commands = [
        f'{compose_cmd} {file_flags} config',
        f'{compose_cmd} {file_flags} up --build -d'
    ]
    stop_command = f'{compose_cmd} {file_flags} down'
    notes = []
    env_file = Path(working_dir) / ".env"
    if env_file.exists():
        notes.append(".env file detected (used automatically by docker compose)")
    access_urls = extract_ports_from_compose(selected_files)
    return {
        "type": "docker-compose",
        "files": selected_files,
        "working_dir": working_dir,
        "commands": commands,
        "stop_command": stop_command,
        "notes": notes,
        "access_urls": access_urls  
    }
def dockerfile_install_agent(info: ProjectInfo) -> Dict[str, Any]:
    dockerfiles = [
        f for f in (info.docker_path or [])
        if Path(f).name.lower().startswith("dockerfile")
        and Path(f).exists()
    ]
    if not dockerfiles:
        return {
            "type": "dockerfile",
            "error": "No Dockerfiles found"
        }
    selected_files = order_dockerfiles(dockerfiles)
    selected_files = [str(Path(f).resolve()) for f in selected_files]
    working_dir = str(Path(selected_files[0]).parent)
    project_name = Path(working_dir).name.lower().replace(" ", "_")
    image_tag = f"{project_name}:latest"
    container_name = f"{project_name}_container"
    ports = extract_ports_from_dockerfile(selected_files)
    if not ports:
        ports = ["3000"]
    port = ports[0]
    port_flags = f"-p {port}:{port}"
    commands = [
        f'docker build -t {image_tag} -f "{selected_files[0]}" "{working_dir}"',
        f'docker run -d --name {container_name} {port_flags} {image_tag}'
    ]
    stop_command = f'docker stop {container_name} && docker rm {container_name}'
    notes = []
    access_urls = [
        f"{project_name}: http://localhost:{port}"
    ]
    return {
        "type": "dockerfile",
        "files": selected_files,
        "working_dir": working_dir,
        "commands": commands,
        "stop_command": stop_command,
        "notes": notes,
        "access_urls": access_urls
    }
def general_install_guide(info: ProjectInfo, mcp_client) -> Dict[str, Any]:
    allowed_files = info.dependency_files
    user_input = f"""
ROLE: You are an installation-command extractor.

CONTEXT
- Project path: {info.path}
- Operating system: {user_os}
- Project type: {info.project_type} (confidence: {info.confidence:.0%})
- Frameworks: {", ".join(info.frameworks) if info.frameworks else "None"}
- Stack summary: {info.stack_summary}

FILES TO READ
Read ONLY these files to determine install/run commands (do not list directories or explore further):
{chr(10).join(f"- {os.path.join(info.path, f)}" for f in info.dependency_files) if info.dependency_files else "- (none listed, infer minimal exploration from project type)"}

DO NOT READ
- README files, docs/, lock files (package-lock.json, yarn.lock, poetry.lock, etc.), or any file not listed above.

GOAL
Output the minimal set of shell commands to install dependencies and run the project successfully.

DECISION RULES (pick ONE best method)
- Do NOT output alternatives.
- Do NOT output OS package manager commands (apt/brew/choco) unless explicitly required AND essential.
- Do NOT include "cd ..." unless required (assume commands run from the project root at {info.path}).

COMMAND RULES
- Output ONLY executable commands.
- Include ONLY:
  1) install command(s)
  2) exactly ONE run command (the best default for local development; if none, use the primary production start command)
- All entries MUST be unique (no duplicates, even if they would be valid).
- Do NOT include comments, prefixes, prompt symbols, code fences, markdown, explanations, or extra keys.

FORBIDDEN COMMAND TYPES
- Do NOT include publish/package/release commands.
- Do NOT include deployment commands.
- Do NOT include containerization commands.
- Do NOT include build-only commands unless required before running.
- Prefer local development execution commands.

OUTPUT FORMAT (MUST MATCH EXACTLY)
Return ONLY valid JSON with this exact shape:

{{
  "commands": [
    "<install command 1>",
    "<install command 2 (optional)>",
    "<single run command>"
  ]
}}

VALIDATION
- The last entry in "commands" MUST be the single run command.
- Do not return empty commands. If uncertain, still choose the most likely working commands based on files.
"""
    result = run_agent(
        llm_client=get_client(),
        mcp_client=mcp_client,
        user_input=user_input,
        allowed_files=allowed_files
    )
    print("[INSTALL GUIDE RESULT]", result)
    return result
def fix_setup_error(failed_command: str, exit_code: int, error_message: str = "", project_path: str = "") -> Dict[str, Any]:
    print("\n" + "="*80)
    print("[DEBUG] fix_setup_error() called")
    print(f"  Command: {failed_command}")
    print(f"  Exit Code: {exit_code}")
    print(f"  Error Message: {error_message}")
    print(f"  Project Path: {project_path}")
    print("="*80)
    
    prompt = f"""
You are a setup troubleshooting expert helping fix failed setup commands.

FAILED COMMAND:
{failed_command}

CONTEXT:
- Exit Code: {exit_code}
- Operating System: {user_os}
{f"- Error Output: {error_message}" if error_message else "- No error output provided"}
{f"- Project Path: {project_path}" if project_path else ""}

YOUR TASK:
1. Analyze WHY this command failed
2. Suggest the MOST LIKELY fix
3. Provide 2-3 ALTERNATIVE commands to try
4. Explain next steps

IMPORTANT RULES FOR COMMANDS:
- Use simple, copy-paste ready commands
- NO unnecessary quotes around paths
- If the original command uses "docker compose", keep it (not "docker-compose")
- Commands must be executable directly
- Avoid special escaping unless absolutely necessary
- Use single file at a time if multiple files cause issues

Return ONLY valid JSON (no markdown code blocks):
{{
  "suggestion": "Explanation of the problem and what to do",
  "alternative_commands": ["command1", "command2", "command3"],
  "next_steps": "Instructions after running the fix"
}}

EXAMPLES:
✓ Good: docker compose -f compose.yml up -d
✓ Good: npm cache clean --force && npm install
✗ Bad: docker compose -f "compose.yml"
✗ Bad: npm \\ install
"""
    
    print("[DEBUG] Prompt created, calling Groq API...")

    try:
        print("[DEBUG] Creating Groq completion...")
        response = get_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        print("[DEBUG] API Response received")
        print(f"[DEBUG] Response choices: {len(response.choices)}")
        
        raw_response = response.choices[0].message.content.strip()
        print(f"[DEBUG] Raw AI response:\n{raw_response}\n")
        
        parsed = safe_parse_ai_json(raw_response, {
            "suggestion": "An error occurred. Please check your command and try again.",
            "alternative_commands": [],
            "next_steps": ""
        })
        
        print(f"[DEBUG] Parsed JSON: {parsed}")
        
        result = {
            "success": True,
            "suggestion": parsed.get("suggestion", ""),
            "alternative_commands": parsed.get("alternative_commands", []),
            "next_steps": parsed.get("next_steps", ""),
            "raw": raw_response
        }
        
        print(f"[DEBUG] Returning success result: {result}")
        print("="*80 + "\n")
        
        return result
        
    except Exception as e:
        print(f"[DEBUG ERROR] Exception occurred: {type(e).__name__}")
        print(f"[DEBUG ERROR] Error message: {str(e)}")
        import traceback
        print(f"[DEBUG ERROR] Traceback:\n{traceback.format_exc()}")
        
        error_result = {
            "success": False,
            "error": str(e),
            "suggestion": "Unable to connect to AI service",
            "alternative_commands": [],
            "next_steps": "Check your internet connection and try again"
        }
        
        print(f"[DEBUG] Returning error result: {error_result}")
        print("="*80 + "\n")
        
        return error_result

