from markdown_extract import MarkdownExtractor
import platform
import distro
import subprocess
import json
import yaml
from pathlib import Path
from typing import  List
def get_system_info() -> str:
    system = platform.system()
    if system == "Linux":
        return f"{distro.name(pretty=True)} {distro.version(pretty=True)}"
    elif system == "Windows":
        release = platform.release()
        version = platform.version()
        return f"Windows {release} (build {version})"
    elif system == "Darwin":
        mac_ver = platform.mac_ver()[0]
        return f"macOS {mac_ver}"
    else:
        return f"{system} (unknown version)"
def docker_exists() -> bool:
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    """
TARGET_KEYWORDS = [
    "install", "setup", "usage", "run", "getting started",
    "quickstart", "execute", "deploy", "how to run"
]
MAX_MD_CHARS = 3000  
def extract_relevant_readme_sections(md_text: str, max_chars: int = MAX_MD_CHARS) -> str:
    try:
        extractor = MarkdownExtractor(md_text)
        sections = []
        for keyword in TARGET_KEYWORDS:
            sec = extractor.get_section(keyword)
            if sec:
                sections.append(sec)
        combined = "\n\n".join(sections).strip()
        return combined[:max_chars]
    except Exception:
        # fallback: return first max_chars of raw content
        return md_text[:max_chars]
    """
def detect_compose_command() -> str:
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return "docker compose"
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return "docker-compose"
    except Exception:
        pass

    return "docker compose" 
def extract_ports_from_compose(files: List[str]) -> List[str]:
    urls = []
    for file in files:
        try:
            content = Path(file).read_text()
            data = yaml.safe_load(content)

            if not data or "services" not in data:
                continue

            for service_name, service in data["services"].items():
                ports = service.get("ports", [])

                for port in ports:
                    if isinstance(port, str):
                        parts = port.split(":")
                        if len(parts) >= 2:
                            host_port = parts[-2]
                            urls.append(f"{service_name}: http://localhost:{host_port}")
        except Exception:
            continue
    return list(set(urls))
def extract_ports_from_dockerfile(files: List[str]) -> List[str]:
    urls = []

    for file in files:
        try:
            content = Path(file).read_text()

            exposes = re.findall(r"EXPOSE\s+([0-9\s]+)", content, re.IGNORECASE)

            for exp in exposes:
                for port in exp.split():
                    if port.isdigit():
                        urls.append(f"container: http://localhost:{port}")

        except Exception:
            continue

    return list(set(urls))
def order_compose_files(files: List[str]) -> List[str]:
    base, override, others = [], [], []
    for f in files:
        name = Path(f).name.lower()
        if name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            base.append(f)
        elif "override" in name:
            override.append(f)
        else:
            others.append(f)
    return base + others + override
def safe_parse_ai_json(output: str, fallback: List[str]) -> List[str]:
    try:
        parsed = json.loads(output)
        if isinstance(parsed, (list, dict)):
            return parsed
    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"[DEBUG] Error parsing JSON: {e}")
    return fallback
def order_dockerfiles(files: List[str]) -> List[str]:
        priority = [
            "dockerfile",
            "dockerfile.prod",
            "dockerfile.production",
            "dockerfile.dev",
            "dockerfile.test",
            "dockerfile.staging"
        ]

        ordered = []
        others = []

        for f in files:
            name = Path(f).name.lower()

            if name in priority:
                ordered.append(f)
            else:
                others.append(f)

        return ordered + others