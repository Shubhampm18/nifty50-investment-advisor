"""Private, persistent user-preference memory for the advisor."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import DeleteResult, EditResult, WriteResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREFERENCES_FILENAME = "PREFERENCES.md"
PREFERENCES_MEMORY_PATH = f"/memories/{PREFERENCES_FILENAME}"
PREFERENCES_TEMPLATE = "# Saved user preferences\n\n"
PREFERENCE_CATEGORIES = (
    "Report style",
    "Research interests",
    "Investment horizon",
    "Risk constraints",
)


def default_memory_directory() -> Path:
    """Return this OS user's application-data directory for private memory."""
    if os.name == "nt":
        base = Path(
            os.environ.get(
                "LOCALAPPDATA",
                Path.home() / "AppData" / "Local",
            )
        )
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )

    return base / "Nifty50InvestmentAdvisor" / "memory"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _resolve_memory_directory(memory_directory: str | Path | None) -> Path:
    directory = (
        Path(memory_directory)
        if memory_directory is not None
        else default_memory_directory()
    )
    resolved = directory.expanduser().resolve()
    if _is_within(resolved, PROJECT_ROOT.resolve()):
        raise ValueError("User memory must be stored outside the project directory.")
    return resolved


class PrivateMemoryFilesystemBackend(FilesystemBackend):
    """Filesystem backend that protects the preference file and prevents deletion."""

    def _restrict_file_permissions(self, file_path: str) -> None:
        if os.name != "nt":
            self._resolve_path(file_path).chmod(0o600)

    def write(self, file_path: str, content: str) -> WriteResult:
        result = super().write(file_path, content)
        if result.error is None:
            self._restrict_file_permissions(file_path)
        return result

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        result = await super().awrite(file_path, content)
        if result.error is None:
            self._restrict_file_permissions(file_path)
        return result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = super().edit(file_path, old_string, new_string, replace_all)
        if result.error is None:
            self._restrict_file_permissions(file_path)
        return result

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = await super().aedit(
            file_path,
            old_string,
            new_string,
            replace_all=replace_all,
        )
        if result.error is None:
            self._restrict_file_permissions(file_path)
        return result

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(
            error=(
                "Preferences can only be cleared with the deliberate CLI "
                "command `nifty50-advisor memory-clear --confirm`."
            )
        )

    async def adelete(self, file_path: str) -> DeleteResult:
        return self.delete(file_path)


def _preferences_path(memory_directory: str | Path | None = None) -> Path:
    return _resolve_memory_directory(memory_directory) / PREFERENCES_FILENAME


def create_memory_backend(
    memory_directory: str | Path | None = None,
) -> PrivateMemoryFilesystemBackend:
    """Create the persistent backend and initialize an empty preference file."""
    directory = _resolve_memory_directory(memory_directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        directory.chmod(0o700)

    backend = PrivateMemoryFilesystemBackend(
        root_dir=directory,
        virtual_mode=True,
    )
    preferences_path = directory / PREFERENCES_FILENAME
    if preferences_path.is_symlink():
        raise ValueError("The user-preferences memory file cannot be a symlink.")
    if not preferences_path.exists():
        result = backend.write(f"/{PREFERENCES_FILENAME}", PREFERENCES_TEMPLATE)
        if result.error is not None:
            raise OSError(
                "Could not initialize user-preferences memory: "
                f"{result.error}"
            )
    elif not preferences_path.is_file():
        raise ValueError("The user-preferences memory path must be a regular file.")
    elif os.name != "nt":
        preferences_path.chmod(0o600)

    return backend


def read_preferences(memory_directory: str | Path | None = None) -> str | None:
    """Read saved preferences without creating a memory directory or file."""
    preferences_path = _preferences_path(memory_directory)
    if preferences_path.is_symlink():
        raise ValueError("The user-preferences memory file cannot be a symlink.")
    if not preferences_path.is_file():
        return None
    return preferences_path.read_text(encoding="utf-8")


def has_saved_preferences(content: str | None) -> bool:
    """Return whether the memory file contains preferences beyond its header."""
    return bool(content and content.strip() != PREFERENCES_TEMPLATE.strip())


def clear_preferences(memory_directory: str | Path | None = None) -> None:
    """Clear saved preferences while retaining the empty memory file."""
    backend = create_memory_backend(memory_directory)
    result = backend.write(f"/{PREFERENCES_FILENAME}", PREFERENCES_TEMPLATE)
    if result.error is not None:
        raise OSError(f"Could not clear user-preferences memory: {result.error}")


def save_preference(
    category: str,
    preference: str,
    memory_directory: str | Path | None = None,
) -> str:
    """Append a preference only when the user explicitly submits it."""
    if category not in PREFERENCE_CATEGORIES:
        raise ValueError("Choose a supported preference category.")
    if not isinstance(preference, str) or not preference.strip():
        raise ValueError("Preference text cannot be empty.")

    cleaned = " ".join(preference.split())
    if len(cleaned) > 500:
        raise ValueError("Preference text must be 500 characters or fewer.")

    current = read_preferences(memory_directory)
    content = current if has_saved_preferences(current) else PREFERENCES_TEMPLATE
    updated = f"{content.rstrip()}\n- **{category}:** {cleaned}\n"

    backend = create_memory_backend(memory_directory)
    result = backend.write(f"/{PREFERENCES_FILENAME}", updated)
    if result.error is not None:
        raise OSError(f"Could not save user preference: {result.error}")

    return updated
