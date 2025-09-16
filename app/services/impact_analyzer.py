import os
from services.code_analyzer.cs_code_analyzer import analyze_cs_file_with_roslyn


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
                return {"impacted": [], "skipped": []}

            impacted_entities, skipped = [], []

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

                    # Decide which path and which refs to try
                    if is_deleted:
                        path = old_path
                        if not path:
                            skipped.append({"file": path_for_check, "reason": "deleted_file but old_path missing"})
                            continue
                        refs_to_try = [base_ref, mr.target_branch]  # old content
                    else:
                        path = new_path
                        if not path:
                            skipped.append({"file": path_for_check, "reason": "no new_path to read"})
                            continue
                        refs_to_try = [head_ref, mr.source_branch, mr.target_branch]  # new content

                    ext = self.get_extension(path)
                    handler = self.get_handler(ext)
                    if not handler:
                        skipped.append({"file": path, "reason": f"no handler for {ext}"})
                        continue

                    # Fetch content robustly
                    try:
                        file_content = self._try_get_file_content(project, path, refs_to_try)
                    except Exception as fe:
                        skipped.append({"file": path, "reason": f"fetch failed @ {refs_to_try}: {fe}"})
                        continue

                    entities = handler(file_content)

                    if is_deleted:
                        if entities:
                            impacted_entities.append({
                                "file": path,
                                "change": "deleted",
                                "impacted": [{
                                    "type": ent["Type"],
                                    "name": ent["Name"],
                                    "start_line": ent["StartLine"],
                                    "end_line": ent["EndLine"],
                                    "why": "file deleted"
                                } for ent in entities]
                            })
                        else:
                            skipped.append({"file": path, "reason": "no entities found in deleted file"})
                        continue

                    changed_lines = set(self.get_changed_lines_from_diff(diff_text))
                    impacted = self.get_impacted_entities(entities, changed_lines)
                    if impacted:
                        for imp in impacted:
                            imp["changed_lines"] = sorted(
                                ln for ln in changed_lines if imp["start_line"] <= ln <= imp["end_line"]
                            )
                            imp["snippet"] = self._slice_snippet(
                                file_content, imp["start_line"], imp["end_line"], changed_lines
                            )
                        impacted_entities.append({
                            "file": path,
                            "change": "new" if is_new else ("renamed" if is_renamed else "modified"),
                            "impacted": [{**imp, "why": "overlaps changed lines"} for imp in impacted]
                        })

                except Exception as per_file_err:
                    skipped.append({
                        "file": file.get("new_path") or file.get("old_path") or "?",
                        "reason": f"unexpected: {per_file_err}"
                    })
                    continue

            return {"impacted": impacted_entities, "skipped": skipped}

        except Exception as e:
            return {"impacted": [], "skipped": [], "error": f"Error at MR level: {e}"}

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
        # Final backstops
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

    def _slice_snippet(self, content: str, start: int, end: int, changed_lines: set[int], ctx: int = 3) -> str | None:
        lines = content.splitlines()
        # changed lines within the entity range
        local = sorted([ln for ln in changed_lines if start <= ln <= end])
        if not local:
            return None
        s = max(local[0] - 1 - ctx, 0)             # 1-based -> 0-based
        e = min(local[-1] - 1 + ctx, len(lines)-1)
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
            # Add more handlers here:
            # '.py': analyze_py_file_with_ast,
            # '.ts': analyze_ts_file_with_parser,
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
            elif line.startswith(" "):  # context
                a_line += 1; b_line += 1
            elif line.startswith("-"):  # removed from old -> modification candidate
                a_line += 1
            elif line.startswith("+"):  # added to new (or modification counterpart)
                changed.add(b_line)
                b_line += 1
        return changed

    def get_impacted_entities(self, entities, changed_lines):
        impacted = []
        for ent in entities:
            entity_lines = set(range(ent['StartLine'], ent['EndLine'] + 1))
            if changed_lines & entity_lines:
                impacted.append({
                    "type": ent["Type"],
                    "name": ent["Name"],
                    "start_line": ent["StartLine"],
                    "end_line": ent["EndLine"]
                })
        return impacted
