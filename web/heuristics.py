"""A fast, dependency-free regex pre-scan.

This powers the **SCHEMATIC** (offline) mode of the UI: when no ANTHROPIC_API_KEY
is set, the server still produces real findings tied to the actual fetched code
by pattern-matching well-known dangerous constructs. It mirrors the orchestrator
-> reviewer shape (each pattern maps to a category) so the visualization is
faithful even without the model.

It is intentionally simple and high-precision-leaning — it is a demo aid and a
first-pass triage, never a replacement for the LLM reviewers or real SAST.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Rule:
    pattern: re.Pattern
    category: str
    severity: str
    title: str
    explanation: str
    fix: str


_RULES: list[Rule] = [
    Rule(re.compile(r"\beval\s*\("), "injection", "critical",
         "Use of eval()",
         "eval() executes arbitrary code; with any attacker-influenced input this is remote code execution.",
         "Replace with a safe parser (ast.literal_eval for literals, json.loads for data)."),
    Rule(re.compile(r"\bexec\s*\("), "injection", "high",
         "Use of exec()",
         "exec() runs arbitrary statements; untrusted input leads to code execution.",
         "Avoid exec(); use an explicit dispatch table or validated parameters."),
    Rule(re.compile(r"shell\s*=\s*True"), "injection", "high",
         "subprocess with shell=True",
         "shell=True interprets the command string through the shell, enabling command injection.",
         "Pass arguments as a list and drop shell=True: subprocess.run([...])."),
    Rule(re.compile(r"\bos\.system\s*\("), "injection", "high",
         "os.system() call",
         "os.system runs a string through the shell; injectable with any user input.",
         "Use subprocess.run([...]) with an argument list."),
    Rule(re.compile(r"\bpickle\.loads?\s*\("), "deserialization", "critical",
         "Unsafe pickle deserialization",
         "pickle.load/loads on untrusted data executes arbitrary code during unpickling.",
         "Use a safe format (JSON) or a schema-validated deserializer."),
    Rule(re.compile(r"yaml\.load\s*\((?![^)]*Safe)"), "deserialization", "high",
         "yaml.load without SafeLoader",
         "yaml.load can instantiate arbitrary Python objects via tags.",
         "Use yaml.safe_load() and validate the result."),
    Rule(re.compile(r"hashlib\.(md5|sha1)\s*\("), "cryptography", "medium",
         "Weak hash function",
         "MD5/SHA-1 are broken for security use (collisions; too fast for passwords).",
         "Use SHA-256+ for integrity, and a slow KDF (bcrypt/scrypt/argon2) for passwords."),
    Rule(re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]{6,}['\"]"),
         "secrets", "high",
         "Hardcoded credential",
         "A secret committed to source is exposed to anyone with repository access.",
         "Load secrets from environment variables or a secrets manager; rotate the leaked value."),
    Rule(re.compile(r"(?i)(SELECT|INSERT|UPDATE|DELETE)\b.*(%s|%\s*\(|\"\s*\+|'\s*\+|\.format\(|f['\"])"),
         "injection", "high",
         "Possible SQL injection",
         "SQL assembled by string concatenation/formatting allows query manipulation.",
         "Use parameterized queries / bound parameters instead of building SQL strings."),
    Rule(re.compile(r"verify\s*=\s*False"), "misconfiguration", "medium",
         "TLS verification disabled",
         "verify=False disables certificate validation, enabling man-in-the-middle attacks.",
         "Remove verify=False; fix the underlying certificate trust issue instead."),
    Rule(re.compile(r"debug\s*=\s*True"), "misconfiguration", "medium",
         "Debug mode enabled",
         "Debug mode can expose an interactive debugger and stack traces in production.",
         "Disable debug in any non-development environment."),
]


def scan(content: str) -> list[dict]:
    """Return a list of finding dicts for a single file's content."""
    findings: list[dict] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue  # skip comment-only lines (our sample file is heavily commented)
        for rule in _RULES:
            if rule.pattern.search(line):
                findings.append({
                    "category": rule.category,
                    "severity": rule.severity,
                    "title": rule.title,
                    "line": lineno,
                    "explanation": rule.explanation,
                    "suggested_fix": rule.fix,
                    "confidence": "medium",
                })
    return findings
