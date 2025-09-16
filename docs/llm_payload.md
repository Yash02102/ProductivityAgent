# LLM Payload Specification

This document explains the structure of the payload we send to the LLM when extracting functional keywords (`LLMClient.extract_keywords`).

## Overview

The client prepends a system prompt (`utils.prompts.extract_functional_prompt`) and then sends a human message whose content is JSON. The JSON bundles:

- Impacted code entities (grouped by file and symbol block)
- Aggregated impact summary metadata
- Optional Jira issue context (sanitized and truncated)

The LLM responds using the `FunctionalKeywordSummary` pydantic schema (categories + JQL terms).

## Top-level JSON

```jsonc
{
  "files": [ /* required when there is impacted code */ ],
  "summary": { /* optional aggregation */ },
  "jira": { /* optional issue snippet */ }
}
```

### `files`
An array describing each impacted source file. Entries with no impacted blocks are pruned before sending.

| Field      | Type      | Notes |
|------------|-----------|-------|
| `path`     | string    | Repository path (new or old path from MR).
| `language` | string    | Language guess (e.g. `csharp`).
| `change`   | string    | Change type (`new`, `modified`, `renamed`, `deleted`).
| `blocks`   | array     | Symbol blocks, described below.

### Symbol block

Each block summarises a code entity that overlaps changed lines.

| Field          | Type           | Notes |
|----------------|----------------|-------|
| `location`     | string or null | Fully qualified path (namespace + containers + name). Fallback derived from `symbol`.
| `kind`         | string or null | e.g. `class`, `method`, `property`.
| `name`         | string or null | Simple name of the symbol.
| `namespace`    | string or null | Declared namespace.
| `containers`   | array of str   | Parent types (outer classes, records, etc.).
| `signature`    | string or null | Human-readable signature.
| `span`         | object         | `{ "start_line": int, "end_line": int, ... }` per analyzer data.
| `changed_lines`| array<int>     | 1-based line numbers touched inside the block.
| `code`         | string or null | Snippet with change markers (`>>`).

These values come directly from `ImpactAnalyzer`'s grouped blocks, so any optional field may be omitted/null.

### `summary`

If the impact analyzer produced aggregated metadata, it is passed through unchanged:

```jsonc
"summary": {
  "files": ["path/to/file.cs", ...],
  "namespaces": ["Company.Product"],
  "containers": ["OrderService"],
  "symbols": ["Calculate"],
  "qualified_symbols": ["Company.Product.OrderService.Calculate"],
  "kinds": ["method", "class"]
}
```

All fields are optional lists. The LLM can use them for quick keyword hints.

### `jira`

Optional Jira context included when `jira_issue_details` is available:

| Field         | Source                                     | Truncation |
|---------------|--------------------------------------------|------------|
| `summary`     | `issue.fields.summary`                     | Clipped to 300 chars |
| `description` | Rich text cleaned via `_jira_plain_text()` | Clipped to 1,200 chars |

Formatting removes Atlassian macros, `{code}` blocks, and Jira link markup.

## Prompt Wrapping

Messages sent to the LLM look like:

```python
messages = [
    SystemMessage(content=extract_functional_prompt),
    HumanMessage(content=json.dumps(payload))
]
```

The system prompt instructs the model on the desired output shape (see `utils/prompts.py`). The human message is **raw JSON** (not Markdown) to reduce parsing ambiguity.

## Expected Output

The LLM returns an instance of `FunctionalKeywordSummary` via LangChain's structured output glue:

```jsonc
{
  "categories": [
    {
      "name": "Payments",
      "confidence": 0.8,
      "keywords": [ { "keyword": "invoice" }, ... ]
    }
  ],
  "jql_terms": ["invoice", "payment", "order"]
}
```

After invocation, the client lowercases and trims `jql_terms`, keeping the first 12 terms of length 2–40.

## Error Handling

- If the LLM call fails, the method raises `Exception("LLM error: ...")` so callers can fall back to heuristic keyword extraction.
- When the LLM is disabled (`LLM_BASE_URL` or `LLM_API_KEY` missing), `extract_keywords` returns `None` and the graph uses heuristics.

## Extending the Payload

When adding new parsers or impacted metadata:

1. Ensure the Python impact analyzer includes the new data in its `blocks` or `summary` structure.
2. Update `_format_block` if additional symbol attributes are needed.
3. Keep the payload JSON stable; avoid embedding binary or extremely large blobs (snippets are already trimmed with context).
4. Document changes here so prompt authors and downstream consumers understand the available context.
