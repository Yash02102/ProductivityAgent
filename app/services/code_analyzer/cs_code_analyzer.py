from __future__ import annotations

import json
import subprocess
from typing import Any

from config import settings


def analyze_cs_file_with_roslyn(content: str) -> dict[str, Any]:
    """Analyze a C# source file and normalize results into the generic parser contract."""
    analysis = {"language": "csharp", "symbols": []}

    analyze_exe = settings.cs_code_analyzer
    if not analyze_exe:
        return analysis

    try:
        result = subprocess.check_output(
            ["dotnet", analyze_exe, "-"],
            input=content,
            text=True,
            encoding="utf-8",
            stderr=subprocess.STDOUT,
            timeout=20,
        )
        payload = json.loads(result)
    except subprocess.CalledProcessError as e:
        print(e)
        return analysis
    except Exception:
        return analysis

    analysis["symbols"] = _normalize_symbols(payload)
    return analysis


def _normalize_symbols(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict[str, Any]] = []
    for node in raw_items:
        if not isinstance(node, dict):
            continue

        display = (
            node.get("DisplayName")
            or node.get("Signature")
            or node.get("Name")
            or node.get("Identifier")
            or ""
        )
        identifier = node.get("Name") or node.get("Identifier") or display

        qualifiers, leaf = _split_symbol(identifier)
        namespace = node.get("Namespace") or node.get("NamespaceName")

        symbol = {
            "kind": node.get("Type") or node.get("Kind") or "symbol",
            "display_name": display or leaf or identifier,
            "name": leaf or identifier,
            "qualifiers": qualifiers,
        }
        if namespace:
            symbol["namespace"] = namespace
        signature = node.get("Signature") or node.get("DisplaySignature")
        if signature:
            symbol["signature"] = signature
        qualified_name = node.get("QualifiedName") or node.get("FullName")
        if not qualified_name:
            parts = [*qualifiers]
            if leaf:
                parts.append(leaf)
            qualified_name = ".".join(parts)
        if qualified_name:
            symbol["qualified_name"] = qualified_name

        span = {
            "start": {
                "line": node.get("StartLine"),
                "column": node.get("StartColumn"),
            },
            "end": {
                "line": node.get("EndLine"),
                "column": node.get("EndColumn"),
            },
        }

        normalized.append({
            "symbol": symbol,
            "span": span,
        })

    return normalized


def _split_symbol(identifier: str) -> tuple[list[str], str]:
    if not identifier:
        return [], ""

    parts = [part for part in identifier.split(".") if part]
    if len(parts) <= 1:
        return [], identifier

    return parts[:-1], parts[-1]
