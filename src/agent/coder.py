from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

CODE_BLOCK_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n(.*?)```", re.DOTALL)
FILE_TAG_RE = re.compile(r"FILE:\s*([^\n\r]+)", re.IGNORECASE)


def maybe_save_code(reply: str, workspace: Path, open_vscode: bool = True) -> Path | None:
    """If the LLM reply includes `FILE: <filename>` and a code block, write it to workspace."""
    file_match = FILE_TAG_RE.search(reply)
    code_match = CODE_BLOCK_RE.search(reply)
    if not file_match or not code_match:
        return None

    rel_name = file_match.group(1).strip().strip("`'\"")
    safe_name = Path(rel_name).name
    if not safe_name:
        return None

    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / safe_name
    target.write_text(code_match.group(1).strip() + "\n", encoding="utf-8")
    log.info("Agent wrote code file: %s", target)

    if open_vscode:
        try:
            subprocess.Popen(["code", str(target)], shell=True)
        except Exception as exc:
            log.debug("VS Code launch skipped: %s", exc)
    return target
