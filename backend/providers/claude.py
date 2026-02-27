"""Claude CLI provider implementation."""

import subprocess
import sys
import tempfile

from .base import AIProvider

_DEFAULT_PROMPT_TEMPLATE = (
    "Please work on the following feature:\n\n"
    "Feature #{feature_id} [{category}]: {name}\n\n"
    "Description:\n{description}\n\n"
    "Steps:\n{steps}"
)


class ClaudeProvider(AIProvider):
    """Spawns a Claude CLI process for autopilot feature work.

    On Windows, wraps the command in PowerShell (pwsh then powershell.exe
    as fallback) to allow reading the prompt from a temp file.
    On other platforms, invokes claude directly with --print.
    """

    def get_provider_name(self) -> str:
        return "claude"

    def spawn_process(self, feature, settings: dict, working_dir: str) -> subprocess.Popen:
        """Spawn a background Claude CLI process and return the Popen handle.

        Raises:
            RuntimeError:    No PowerShell found on Windows.
            FileNotFoundError: claude CLI not found on non-Windows platforms.
        """
        template = settings.get("claude_prompt_template", _DEFAULT_PROMPT_TEMPLATE)
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(feature.steps))
        prompt = template.format(
            feature_id=feature.id,
            category=feature.category,
            name=feature.name,
            description=feature.description,
            steps=steps_text,
        )

        feature_model = feature.model or "sonnet"

        if sys.platform == "win32":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            ps_cmd = (
                f'claude --model {feature_model} --dangerously-skip-permissions '
                f'--print (Get-Content -LiteralPath "{prompt_file}" -Raw)'
            )
            for ps_exe in ["pwsh", "powershell"]:
                try:
                    return subprocess.Popen(
                        [ps_exe, "-Command", ps_cmd],
                        cwd=working_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except FileNotFoundError:
                    continue

            raise RuntimeError(
                "No PowerShell found. Install PowerShell 7 (pwsh) or ensure powershell.exe is available."
            )
        else:
            try:
                return subprocess.Popen(
                    ["claude", "--model", feature_model, "--dangerously-skip-permissions", "--print", prompt],
                    cwd=working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except FileNotFoundError:
                raise FileNotFoundError("Claude CLI not found. Make sure claude is in your PATH.")
