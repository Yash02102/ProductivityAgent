# Productivity-ai



Agentic service that reads GitLab Merge Requests, pulls Jira issue context, infers impacted code entities, extracts search keywords (LLM or heuristic), and returns a report + suggested Jira Tests.

API: FastAPI (/analyze)

Agent runtime: LangGraph

Integrations: GitLab, Jira, optional LLM (OpenAI-compatible)

Extras: Structured logging, optional OpenTelemetry hooks


## Features

- One POST to analyze an MR and get a markdown report

- LLM-assisted keyword extraction with heuristic fallback

- Resilient: retries, timeouts, error collection (no hard crashes)

- Modular: clients (GitLab/Jira/LLM), services, graph nodes

- Easy local dev: venv + requirements.txt, VS Code debug configs

## Prerequisites

- Python 3.10–3.12

- GitLab personal access token (with MR read scope)

- Jira API token + username (for Atlassian Cloud)

- Optional: LLM gateway/API key (OpenAI-compatible)

- Optional: .NET SDK if you use the Roslyn analyzer (dotnet CLI)




# Productivity AI
## From Merge Request → Actionable Test Plan in minutes

### What it does (bridge):

- Listens to GitLab MR events and the linked Jira issue

- Understands code changes → derives functional impact areas

- Finds the right Jira Tests, then creates/reuses a Test Plan and adds them

- Posts a transparent Jira comment with code summary, impact rationale, confidence, evidence, and test links

### How it works (flow):

- Trigger: MR event (project / MR link)

- Understand: Diffs + impacted files/classes/methods

- Reason: LLM → functional categories with rationale, confidence (★), evidence

- Retrieve: Builds focused JQL terms → fetches candidate Tests

- Orchestrate: Test Plan (by project + component + release target) → create or reuse; add tests

- Feedback: Jira comment: Code Changes, Functional Impact, Tests by Category, Test Plan link

### Why it’s not a black box:

- Each category shows a one-line rationale

- Evidence tokens (files/entities) explain why

- Confidence score (★ to ★★★★★) signals priority

- Full MR + Test Plan links for auditability

### Impact (POC results):

- ⚡ Faster handoff: MR→tests in < 2 min (was 30–60 min manual)

- 🎯 Higher relevance: tests grouped by functional area (less noise)

- 🧪 Better coverage: test discovery across existing suites

- 🔁 Idempotent: reuses plan when present; adds only missing tests

### Example outcomes (from runs shown):

- Categories like “shipment patching”, “ship-from validation (TR)”, “FGAs / shipping options”

- Evidence: UnifiedBasketManager, QuoteExtension.IsTurkey, ShipmentDetailsMapper

- Confidence: ★★★★☆–★★★★★ with clear rationale

- Test Plan created & 40+ tests added automatically

### Controls & guardrails:

- Uses only MR diffs + Jira summary/description

- Component + Release Target drive plan reuse

- Pluggable search/filters; configurable thresholds

- Tracelink AI = modern, transparent test-impact analysis that closes the gap between code and QA.
