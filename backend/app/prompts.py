from pathlib import Path

from app.config import get_settings


PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "assistant_prompt.txt"


def load_assistant_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_history_text(history: list) -> str:
    if not history:
        return "Sem histórico anterior."

    lines = []
    for message in history[-8:]:
        role = "Utilizador" if message.role == "user" else "Assistente"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def api_key_help_text() -> str:
    settings = get_settings()
    return (
        "Gemini não está configurado. Define GOOGLE_API_KEY no ficheiro "
        f"{settings.project_root / 'backend' / '.env'} e reinicia a API."
    )
