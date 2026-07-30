from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "OpenAI API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b"),
    "Vercel Blob token": re.compile(r"\bvercel_blob_rw_[A-Za-z0-9_-]{20,}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Credential URL": re.compile(r"\b(?:postgres(?:ql)?|mysql)://[^:\s/]+:[^@\s/]+@"),
}
ALLOWED_EXAMPLE = re.compile(
    r"(example|placeholder|testing-only|test-secret|emotion:emotion@(?:localhost|postgres))",
    re.I,
)


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / value.decode("utf-8") for value in output.split(b"\0") if value]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if ALLOWED_EXAMPLE.search(line):
                continue
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{line_number}: {label}")
    if findings:
        print("Potential committed secrets found:")
        print("\n".join(findings))
        return 1
    print("Secret scan passed: no high-confidence credentials in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
