# Group 5 TextFSM Normalization Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an end-to-end TextFSM normalization pipeline that standardizes network device command output for both the on-prem agent and cloud ingestion paths, with vendor-aware coverage, graceful fallbacks, and observable failure modes.

**Architecture:** Normalize at the edge first, then keep the cloud ingestion contract identical so both paths share the same schema and behavior. The pipeline should prefer vendor-specific TextFSM templates, fall back to a clearly defined permissive parser when a template is missing, and emit clearly typed normalization results that downstream ML and API layers can consume without vendor-specific branching.

**Tech Stack:** Python 3.11, TextFSM, ntc-templates, Pydantic, pytest, Docker Compose, FastAPI, async HTTP clients

---

## Context

TextFSM normalization is the critical path for ML because it converts raw command output into stable structured records before feature extraction, classification, and storage. The repository already has sanitizer and parser-adjacent groundwork, including Tier 1 TextFSMSanitizer stubs, tiered sanitization, and planning docs for the agent pipeline. Group 5 extends that foundation into a full normalization layer that can be exercised from the local agent and reused by cloud-side ingestion.

## Design Principles

- Prefer template coverage over heuristics when a vendor template exists.
- Keep the normalized record schema vendor-neutral and ML-friendly.
- Make fallback behavior explicit instead of silently degrading.
- Preserve raw input references in metadata, but do not duplicate sensitive raw configs in cloud storage.
- Ensure the agent and cloud paths validate against the same schema contract.

## Proposed Approaches

### Option A: Shared normalization library with thin adapters

Create a reusable normalization package inside the agent service tree that is also exposed as a shared contract module for the API to import or mirror. The agent calls it directly during collection, while the API uses the same schema definitions during ingest/validation to confirm payload compatibility.

Trade-off: best long-term consistency, slightly more upfront refactoring.

### Option B: Agent-owned normalization, cloud validation only

Implement normalization exclusively in the agent and have the cloud side only validate the resulting schema.

Trade-off: less cloud complexity, but weaker parity and harder to test end-to-end.

### Option C: Cloud-owned normalization, agent passes raw output

Keep the agent thin and perform normalization in the API after upload.

Trade-off: simpler agent rollout, but conflicts with privacy-first edge processing and expands cloud responsibility.

### Recommendation

Use Option A. It best matches the privacy-first architecture, preserves parity between both paths, and makes template coverage improvements immediately useful everywhere.

## System Design

The normalization layer should expose a single entry point that accepts raw command output, vendor hints, and command metadata, then returns a structured normalized payload with:

- normalized records
- template metadata
- parser method used
- warnings and fallback reasons
- vendor and command identity
- versioned schema information
- template source/version
- parser status and confidence
- normalization timestamp

The agent should normalize immediately after collection and before sanitization/storage handoff. The API should accept the same normalized schema for uploads and use the same Pydantic models for validation, so parity is enforced by code rather than convention.

## Data Flow

1. Collector obtains raw device output and vendor hints.
2. Normalizer resolves a TextFSM template for vendor + command.
3. If a template exists, parse into structured fields and emit canonical records.
4. If no template exists, fall back to a permissive structured parser with an explicit fallback reason.
5. Sanitization runs before cloud upload and the API accepts only sanitized normalized payloads.
6. Upload normalized payload and metadata to the cloud API.
7. API validates schema, stores normalized metadata, and makes the payload available for ML feature extraction.

## Error Handling

- Missing template: return a fallback result with a machine-readable reason code and vendor/command metadata.
- Parse failure: surface a non-fatal error object, preserve the original command identity, and continue with fallback if allowed.
- Unsupported vendor: mark payload as partially normalized rather than failing the entire pipeline unless strict mode is enabled.
- Schema mismatch: reject at validation time with explicit field-level errors.
- Strict mode: reject unknown vendor/command pairs instead of falling back.

## Testing Strategy

### Unit tests

- Template resolution by vendor and command.
- Canonical normalization output for representative vendors.
- Fallback behavior when templates are missing.
- Schema validation for normalized payloads.
- Metadata propagation and version stamping.

### Integration tests

- Agent pipeline test from raw command output to normalized payload to sanitized upload object.
- API ingest validation test using the same schema contract as the agent.
- Vendor coverage test for the top supported templates.

### End-to-end tests

- Containerized test that simulates collection from a sample device family and verifies normalized payload acceptance in the API.
- Regression test for known vendor/command pairs to ensure template changes do not break downstream ML expectations.

## Risks and Mitigations

- Template drift across vendors: maintain a fixture matrix and add regression tests per supported command family.
- Overfitting to a single vendor: keep schema canonical and explicitly vendor-neutral.
- Silent fallback regressions: require fallback reasons in test assertions and logs.
- Duplicate logic between agent and API: centralize schema models and normalization helpers.
- Version skew between agent and API: require contract version checks and compatibility tests.
- Missing operational visibility: emit metrics for template hit rate, fallback rate, and schema rejection rate.

## Open Questions

- Which vendor/command combinations are in scope for the first coverage wave?
- Should strict mode reject unknown templates in production, or always allow fallback?
- Which normalized fields are required for the ML classifier versus optional metadata?
