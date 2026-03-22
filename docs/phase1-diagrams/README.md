# Phase 1 Diagrams

This directory contains Mermaid diagrams documenting the NetDiscoverIT Phase 1 implementation.

## Diagrams

### 1. Architecture (`architecture.mmd`)
High-level system architecture showing:
- Customer network with local agent
- Agent service components
- Cloud platform (API, databases)
- Privacy boundary

### 2. Data Flow (`data-flow.mmd`)
Sequence diagram showing:
- Discovery & collection stage
- Sanitization pipeline (3 tiers)
- Vectorization
- Cloud upload

### 3. Design (`design.mmd`)
Class diagram showing:
- ConfigSanitizer orchestration
- TierResolver logic
- Token system (TokenMapper, TokenType)
- Audit logging (RedactionLogger)
- Individual sanitizer implementations

## Rendering

These diagrams render automatically in:
- GitHub/GitLab Markdown files
- VS Code with Mermaid extension
- Mermaid Live Editor: https://mermaid.live

## Offline Rendering

```bash
# Using Docker
docker run --rm -v $(pwd):/data minlag/mermaid-cli -i architecture.mmd -o architecture.png
```

## Updates

When making architectural changes:
1. Update the relevant `.mmd` file
2. Regenerate static versions if needed
3. Commit both source and rendered images