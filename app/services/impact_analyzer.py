from __future__ import annotations

import os
from typing import Any, Iterable

from app.services.code_analyzer.cs_code_analyzer import analyze_cs_file_with_roslyn


class ImpactAnalyzer:
    def __init__(self, gitlab_client):
        self.gl = gitlab_client

    def get_impacted_code_areas(self, project_id: int, merge_request_id: int):
        try:
            project = self.gl.projects.get(project_id)
            mr = project.mergerequests.get(merge_request_id)

            head_ref, base_ref = self._mr_refs(mr)
            summary = mr.changes()
            mr_diff_files = summary.get("changes", [])
            if not mr_diff_files:
                return {"files": [], "skipped": []}

            impacted_files: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            summary_acc = self._summary_bucket()

            for file in mr_diff_files:
                try:
                    new_path = file.get("new_path")
                    old_path = file.get("old_path")
                    is_new = file.get("new_file", False)
                    is_deleted = file.get("deleted_file", False)
                    is_renamed = file.get("renamed_file", False)
                    is_binary = file.get("binary", False)
                    diff_text = file.get("diff", "")

                    path_for_check = new_path or old_path or ""
                    if is_binary or not self.is_code_file(path_for_check):
                        skipped.append({"file": path_for_check, "reason": "non-code or binary"})
                        continue

                    if is_deleted:
                        path = old_path
                        if not path:
                            skipped.append({"file": path_for_check, "reason": "deleted_file but old_path missing"})
                            continue
                        refs_to_try = [base_ref, mr.target_branch]
                    else:
                        path = new_path
                        if not path:
                            skipped.append({"file": path_for_check, "reason": "no new_path to read"})
                            continue
                        refs_to_try = [head_ref, mr.source_branch, mr.target_branch]

                    ext = self.get_extension(path)
                    handler = self.get_handler(ext)
                    if not handler:
                        skipped.append({"file": path, "reason": f"no handler for {ext}"})
                        continue

                    try:
                        file_content = self._try_get_file_content(project, path, refs_to_try)
                    except Exception as fe:
                        skipped.append({"file": path, "reason": f"fetch failed @ {refs_to_try}: {fe}"})
                        continue

                    analysis_output = handler(file_content)
                    language, symbols = self._unwrap_analysis(analysis_output)
                    language = language or self._language_for_extension(ext)

                    if is_deleted:
                        blocks = self.get_impacted_blocks(symbols, None, file_content, "file deleted")
                        if blocks:
                            impacted_files.append({
                                "path": path,
                                "language": language,
                                "change": "deleted",
                                "blocks": blocks,
                            })
                            self._update_summary(summary_acc, path, blocks)
                        else:
                            skipped.append({"file": path, "reason": "no symbols found in deleted file"})
                        continue

                    changed_lines = set(self.get_changed_lines_from_diff(diff_text))
                    blocks = self.get_impacted_blocks(symbols, changed_lines, file_content, "overlaps changed lines")
                    if blocks:
                        impacted_files.append({
                            "path": path,
                            "language": language,
                            "change": "new" if is_new else ("renamed" if is_renamed else "modified"),
                            "blocks": blocks,
                        })
                        self._update_summary(summary_acc, path, blocks)
                    else:
                        skipped.append({"file": path, "reason": "no symbols overlap changed lines"})

                except Exception as per_file_err:
                    skipped.append({
                        "file": file.get("new_path") or file.get("old_path") or "?",
                        "reason": f"unexpected: {per_file_err}"
                    })
                    continue

            payload = {"files": impacted_files, "skipped": skipped}
            summary = self._finalize_summary(summary_acc)
            if summary:
                payload["summary"] = summary
            return payload

        except Exception as e:
            return {"files": [], "skipped": [], "error": f"Error at MR level: {e}"}

    def _mr_refs(self, mr):
        """Return (head_ref_for_new, base_ref_for_old) with sensible fallbacks."""
        head = None
        base = None
        try:
            refs = getattr(mr, "diff_refs", None) or {}
            head = refs.get("head_sha") or getattr(mr, "sha", None)
            base = refs.get("base_sha") or mr.target_branch
        except Exception:
            pass
        head = head or mr.source_branch or mr.target_branch
        base = base or mr.target_branch
        return head, base

    def _try_get_file_content(self, project, path: str, refs: list[str]) -> str:
        """Try multiple refs until one succeeds; raise the last error if all fail."""
        last_err = None
        for ref in filter(None, refs):
            try:
                return self.get_file_content(project, path, ref)
            except Exception as e:
                last_err = e
                continue
        raise last_err or FileNotFoundError(f"Unable to fetch {path} from any ref")

    def get_impacted_blocks(
        self,
        symbols: list[dict[str, Any]],
        changed_lines: set[int] | None,
        content: str,
        reason: str,
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for entry in symbols:
            block = self._build_block(entry, changed_lines, content)
            if block:
                block["reason"] = reason
                blocks.append(block)
        return blocks

    def _build_block(
        self,
        symbol_entry: dict[str, Any],
        changed_lines: set[int] | None,
        content: str,
        ctx: int = 3,
    ) -> dict[str, Any] | None:
        symbol = symbol_entry.get("symbol") or {}
        span = symbol_entry.get("span") or {}
        start_info = span.get("start") or {}
        end_info = span.get("end") or {}
        start_line = self._safe_int(start_info.get("line"))
        end_line = self._safe_int(end_info.get("line"))
        start_col = self._safe_int(start_info.get("column"))
        end_col = self._safe_int(end_info.get("column"))
        if not start_line or not end_line:
            return None

        if not isinstance(symbol, dict):
            symbol = {}

        identifier = (
            symbol.get("qualified_name")
            or symbol.get("display_name")
            or symbol.get("name")
        ) or ""
        if not symbol.get("name") and identifier:
            name = identifier.split(".")[-1]
            symbol = {**symbol, "name": name}
        if "display_name" not in symbol and identifier:
            symbol = {**symbol, "display_name": identifier}
        if "qualifiers" not in symbol and identifier:
            qualifiers, _leaf = self._split_identifier(identifier)
            if qualifiers:
                symbol = {**symbol, "qualifiers": qualifiers}

        block: dict[str, Any] = {
            "symbol": {k: v for k, v in symbol.items() if v not in (None, "")},
            "span": {"start_line": start_line, "end_line": end_line},
            "changed_lines": [],
        }
        if start_col is not None:
            block["span"]["start_column"] = start_col
        if end_col is not None:
            block["span"]["end_column"] = end_col

        relevant: list[int] = []
        if isinstance(changed_lines, set):
            relevant = [ln for ln in changed_lines if start_line <= ln <= end_line]
            if not relevant:
                return None
            block["changed_lines"] = sorted(relevant)
        elif isinstance(changed_lines, Iterable):
            relevant = [ln for ln in changed_lines if start_line <= ln <= end_line]
            if not relevant:
                return None
            block["changed_lines"] = sorted(relevant)

        snippet = self._slice_snippet(content, start_line, end_line, changed_lines, ctx)
        if snippet:
            block["snippet"] = snippet

        location = self._compose_location(block["symbol"])
        if location:
            block["location"] = location

        return block

    def _slice_snippet(
        self,
        content: str,
        start: int,
        end: int,
        changed_lines: set[int] | None,
        ctx: int = 3,
    ) -> str | None:
        if not content or start is None or end is None or start < 1 or end < 1:
            return None

        lines = content.splitlines()
        if not lines:
            return None

        if not changed_lines:
            s = max(start - 1, 0)
            e = min(end - 1, len(lines) - 1)
            if s > e:
                return None
            out = []
            for i in range(s, e + 1):
                out.append(f"{i+1:5d}   {lines[i]}")
            return "\n".join(out)

        local = sorted([ln for ln in changed_lines if start <= ln <= end])
        if not local:
            return None
        s = max(local[0] - 1 - ctx, 0)
        e = min(local[-1] - 1 + ctx, len(lines) - 1)
        out = []
        for i in range(s, e + 1):
            mark = ">>" if (i + 1) in changed_lines else "  "
            out.append(f"{i+1:5d}{mark} {lines[i]}")
        return "\n".join(out)

    def is_code_file(self, file_path: str) -> bool:
        if not file_path:
            return False
        path = file_path.lower()
        return (
            (path.endswith('.cs') or path.endswith('.py') or path.endswith('.ts'))
            and 'test' not in path and 'spec' not in path
        )

    def get_extension(self, file_path: str) -> str:
        return os.path.splitext(file_path)[1].lower()

    def get_handler(self, ext: str):
        return {
            '.cs': analyze_cs_file_with_roslyn,
        }.get(ext)

    def get_file_content(self, project, file_path: str, branch: str) -> str:
        """Get the content of a file in a project."""
        import base64
        raw = project.files.get(file_path=file_path, ref=branch)
        content = base64.b64decode(raw.content).decode("utf-8", errors="replace")
        return content.lstrip('\ufeff')

    def get_changed_lines_from_diff(self, diff_text: str):
        changed = set()
        a_line = b_line = 0
        for line in diff_text.splitlines():
            if line.startswith("@@"):
                import re
                m = re.search(r"\-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?", line)
                a_line = int(m.group(1) or 0)
                b_line = int(m.group(3) or 0)
            elif line.startswith(" "):
                a_line += 1; b_line += 1
            elif line.startswith("-"):
                a_line += 1
            elif line.startswith("+"):
                changed.add(b_line)
                b_line += 1
        return changed

    def _unwrap_analysis(self, output: Any) -> tuple[str | None, list[dict[str, Any]]]:
        language = None
        raw_symbols: Iterable[Any]
        if isinstance(output, dict):
            language = output.get("language")
            raw_symbols = output.get("symbols") or []
        else:
            raw_symbols = output or []
        symbols: list[dict[str, Any]] = []
        for node in raw_symbols:
            normalized = self._ensure_symbol_entry(node)
            if normalized:
                symbols.append(normalized)
        return language, symbols

    def _ensure_symbol_entry(self, node: Any) -> dict[str, Any] | None:
        if not isinstance(node, dict):
            return None

        symbol = node.get("symbol") or {}
        span = node.get("span") or {}

        start_info = span.get("start") if isinstance(span, dict) else None
        end_info = span.get("end") if isinstance(span, dict) else None

        if not start_info or not end_info:
            start_line = node.get("start_line") or node.get("StartLine")
            end_line = node.get("end_line") or node.get("EndLine")
            start_col = node.get("start_column") or node.get("StartColumn")
            end_col = node.get("end_column") or node.get("EndColumn")
            span = {
                "start": {"line": start_line, "column": start_col},
                "end": {"line": end_line, "column": end_col},
            }
            start_info = span["start"]
            end_info = span["end"]
        else:
            start_line = start_info.get("line")
            end_line = end_info.get("line")

        start_line = self._safe_int(start_info.get("line"))
        end_line = self._safe_int(end_info.get("line"))
        if not start_line or not end_line:
            return None

        if not isinstance(symbol, dict) or not symbol:
            symbol = {
                "kind": node.get("type") or node.get("Type"),
                "name": node.get("name") or node.get("Name"),
                "display_name": node.get("display_name") or node.get("DisplayName") or node.get("Name"),
            }

        identifier = (
            symbol.get("qualified_name")
            or symbol.get("display_name")
            or symbol.get("name")
            or node.get("QualifiedName")
            or node.get("FullName")
            or node.get("Name")
        ) or ""
        if identifier:
            qualifiers, leaf = self._split_identifier(identifier)
            symbol.setdefault("qualified_name", identifier)
            symbol.setdefault("name", leaf or identifier)
            if qualifiers:
                symbol.setdefault("qualifiers", qualifiers)

        namespace = node.get("namespace") or node.get("Namespace") or node.get("NamespaceName")
        if namespace:
            symbol.setdefault("namespace", namespace)
        signature = node.get("signature") or node.get("Signature")
        if signature:
            symbol.setdefault("signature", signature)

        return {"symbol": symbol, "span": span}

    def _split_identifier(self, identifier: str) -> tuple[list[str], str]:
        if not identifier:
            return [], ""
        parts = [part for part in identifier.split(".") if part]
        if len(parts) <= 1:
            return [], identifier
        return parts[:-1], parts[-1]

    def _compose_location(self, symbol: dict[str, Any]) -> str | None:
        parts: list[str] = []
        namespace = symbol.get("namespace")
        if namespace:
            parts.extend([p for p in str(namespace).split(".") if p])
        for qualifier in symbol.get("qualifiers") or []:
            parts.extend([p for p in str(qualifier).split(".") if p and p not in parts])
        name = symbol.get("name") or symbol.get("display_name")
        if name:
            if not parts or parts[-1] != name:
                parts.append(str(name))
        if not parts:
            q = symbol.get("qualified_name") or symbol.get("display_name")
            return q
        return ".".join(parts)

    def _safe_int(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _language_for_extension(self, ext: str) -> str | None:
        return {
            '.cs': 'csharp',
            '.py': 'python',
            '.ts': 'typescript',
        }.get(ext)

    def _summary_bucket(self) -> dict[str, set[str]]:
        return {
            "files": set(),
            "namespaces": set(),
            "containers": set(),
            "symbols": set(),
            "qualified_symbols": set(),
            "kinds": set(),
        }

    def _update_summary(self, summary: dict[str, set[str]], path: str | None, blocks: list[dict[str, Any]]):
        if path:
            summary["files"].add(path)
        for block in blocks:
            symbol = block.get("symbol") or {}
            namespace = symbol.get("namespace")
            if namespace:
                summary["namespaces"].add(namespace)
            for qualifier in symbol.get("qualifiers") or []:
                summary["containers"].add(qualifier)
            name = symbol.get("name")
            if name:
                summary["symbols"].add(name)
            qualified = block.get("location") or symbol.get("qualified_name") or symbol.get("display_name")
            if qualified:
                summary["qualified_symbols"].add(qualified)
            kind = symbol.get("kind")
            if kind:
                summary["kinds"].add(kind)

    def _finalize_summary(self, summary: dict[str, set[str]]) -> dict[str, list[str]]:
        out = {}
        for key, values in summary.items():
            if values:
                out[key] = sorted(values)
        return out
