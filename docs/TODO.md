# NetDiscoverIT — TODO

## Phase 1 Completion (finish what's built)

### Backend — Critical Bugs
- [x] Fix `uuid4(user_id)` → `UUID(user_id)` in `auth.py` refresh token endpoint

### Backend — Stubs to Implement
- [x] `POST /discoveries` — implement job queuing (APScheduler against existing Redis)
- [x] `GET /discoveries/{id}` — implement status fetch
- [x] `POST /api/path-trace` — implement Neo4j `find_path()` endpoint (unlocks PathVisualizer)
- [x] `dependencies.get_current_active_user()` — add `user.is_active` check

### Agent — Stubs to Implement
- [x] `uploader.py` — replace hardcoded `"default-customer"` with org_id from LocalAgent registration
- [x] `uploader.py` — fix auth header: send `X-Agent-Key` not `Bearer` token
- [x] `collector.py` — implement `get_interfaces()`, `get_vlans()`, `get_routing()` per device type
- [x] `collector.py` — implement Nmap auto-discovery (currently only pre-configured devices work)

### Frontend — API Integration
- [x] Auth flow: login form → JWT storage → token refresh
- [x] Replace mock data in `Devices.jsx` with real `GET /devices`
- [x] Replace mock data in `Discoveries.jsx` with real `GET/POST /discoveries`
- [x] Wire `PathVisualizer.jsx` to real path-trace endpoint + Neo4j topology
- [x] Replace mock data in `Dashboard.jsx` with real stats
- [x] `Settings.jsx` — implement (currently empty shell)
- [x] Add global error handling and loading states

### Cleanup
- [x] Consolidate duplicate sanitizer code (agent vs API versions)

---

## Phase 2

### Agent — New Modules
- [ ] `scanner.py` — full Nmap/SNMP network scanning and auto-discovery
- [ ] `topology.py` — CDP/LLDP topology mapping
- [ ] IVRE integration for network recon

### Cloud — Features
- [ ] Discovery job queue with real-time status (WebSocket)
- [ ] Compliance report generation (PCI-DSS, HIPAA, SOX, ISO 27001)
- [ ] External ticketing integration endpoints (ServiceNow, Jira, Slack)
- [ ] Alert delivery workflows (AlertRule → AlertEvent → notify IntegrationConfig)
- [ ] Change management workflow (ChangeRecord lifecycle + ContainerLab simulation)
- [ ] ACL Compliance Vault endpoints (zero-knowledge encrypted storage)
- [ ] Export document generation (PDF, DOCX, Drawio, Visio) + MinIO/S3

### Frontend — Phase 2 Features
- [ ] D3 full topology overview map (all devices, not just path trace)
- [ ] Natural language interface (RAG query input)
- [ ] Compliance report viewer
- [ ] Change management UI (ChangeRecord lifecycle)
- [ ] MSP multi-org switcher

### Infrastructure
- [ ] Rate limiting on API endpoints
- [ ] HTTPS / TLS termination (nginx or Traefik in compose)
- [ ] mTLS for agent-to-cloud (enterprise/gov upgrade path)
