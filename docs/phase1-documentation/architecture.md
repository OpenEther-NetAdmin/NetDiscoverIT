# Architecture

This document describes the system architecture for NetDiscoverIT, covering the major components, their responsibilities, and how they interact to deliver network discovery with privacy-first principles.

## System Overview

NetDiscoverIT follows a distributed architecture with a clear separation between on-premises and cloud components. The on-premises Agent performs all sensitive operations—device connectivity, configuration collection, and sanitization—while the cloud platform handles data storage, visualization, and querying.

This architectural separation is fundamental to the platform's privacy guarantee. No raw configuration data, passwords, or secrets ever leave the customer network. The Agent transmits only sanitized metadata, topology relationships, and vector embeddings to the API service.

## Component Architecture

### Agent Service

The Agent Service is the core on-premises component that runs within the customer's network. It is deployed as a Docker container and never communicates directly with network devices outside the local network segment.

The Agent orchestrates a multi-stage pipeline for network discovery and data preparation. Each stage handles a specific responsibility, passing output to the next stage until sanitized data is ready for upload.

#### Scanner Module

The Scanner module initiates network discovery by probing target networks for reachable devices. It supports multiple discovery methods including SSH connectivity checks, SNMP queries for device information, and Nmap scans for port and service enumeration.

The scanner identifies device characteristics such as vendor, model, operating system version, and management interface addresses. This information becomes the foundation for subsequent collection operations.

Implementation resides in `services/agent/agent/scanner.py`.

#### Collector Module

The Collector module retrieves running configurations from discovered devices. Using SSH connectivity established by the scanner, it executes commands to dump configurations from routers, switches, and firewalls.

The collector handles multi-vendor environments by adapting command syntax based on detected device types. It stores raw configurations in memory only, passing them immediately to the sanitizer for processing.

Implementation resides in `services/agent/agent/collector.py`.

#### Sanitizer Module

The Sanitizer module is the most critical component in the architecture. It strips all sensitive information from configurations before any data leaves the customer network. This module implements the privacy guarantee that defines NetDiscoverIT's value proposition.

The sanitizer employs a three-tier approach for comprehensive coverage. Tier 1 uses TextFSM templates for precise, vendor-specific parsing when templates are available. Tier 2 applies section-aware regex patterns that detect configuration sections like interfaces, routing processes, and apply targeted sanitization rules. Tier 3 serves as a catch-all using aggressive regex patterns to capture any remaining sensitive data that the first two tiers missed.

Each redaction is logged with a hash of the original value, enabling audit and verification without storing actual secrets. The redaction log accompanies uploaded data to provide visibility into what was sanitized.

Implementation resides in `services/agent/agent/sanitizer/`, with the main orchestrator at `services/agent/agent/sanitizer/config_sanitizer.py`.

#### Topology Module

The Topology module discovers network relationships by parsing CDP (Cisco Discovery Protocol) and LLDP (Link Layer Discovery Protocol) neighbor information. It builds a graph of how devices connect to each other, including interface-level details.

This topology data becomes critical for visualizing network architecture, understanding failover paths, and identifying critical infrastructure. The module outputs structured relationship data that the API stores in Neo4j for graph queries.

Implementation resides in `services/agent/agent/topology.py`.

#### Vectorizer Module

The Vectorizer module generates embeddings from sanitized configurations. It converts text configurations into numerical vectors that capture semantic meaning, enabling similarity searches across the configuration database.

The vectorizer produces 768-dimensional embeddings using sentence transformers. These vectors are stored in PostgreSQL with the pgvector extension, enabling efficient similarity queries.

Implementation resides in `services/agent/agent/vectorizer.py`.

#### Uploader Module

The Uploader module transmits processed data to the API service. It authenticates using JWT tokens and sends sanitized device metadata, topology relationships, and vector embeddings in structured payloads.

The uploader handles retry logic and maintains upload state to ensure reliable data transfer even across unreliable network connections.

Implementation resides in `services/agent/agent/uploader.py`.

### API Service

The API Service provides the cloud-side interface for receiving and serving network discovery data. It exposes REST endpoints for agent communication, frontend queries, and administrative operations.

#### Routes and Endpoints

The API organizes functionality around resources: devices, sites, discoveries, scans, configurations, credentials, alerts, and agents. Each resource type has standard CRUD operations plus resource-specific queries.

Routes are defined in `services/api/app/api/routes.py` and follow REST conventions with `/api/v1` prefix.

#### Database Models

PostgreSQL stores all structured data using SQLAlchemy ORM with async support. Models are defined in `services/api/app/models/models.py`.

Key models include Organization for multi-tenant support, User for authentication and authorization, Device for discovered network equipment, Interface for interface-level details, Discovery for scan orchestration, Scan for individual discovery operations, Configuration for configuration snapshots with change tracking, Credential for encrypted device access credentials, and Site for logical grouping of devices.

Vector columns use pgvector with HNSW indexing for efficient similarity search. The vector dimension is 768 to match the embedding model output.

#### Neo4j Integration

Neo4j stores topology graph data separately from the relational database. The graph database excels at relationship queries that would be expensive in SQL, such as finding all devices within two hops of a specific router or identifying potential single points of failure.

The Neo4j client is initialized in `services/api/app/db/neo4j.py`.

#### Background Tasks

The API uses background tasks for long-running operations like large discovery scans, alert processing, and configuration diff analysis. Task definitions are in `services/api/app/tasks/`.

### Frontend Service

The Frontend Service provides the web interface for interacting with NetDiscoverIT. It connects to the API service to fetch and display data, visualize topology graphs, and manage platform configuration.

The frontend uses React with Chakra UI components. State management relies on React Query for server state and React hooks for local state. The component structure separates reusable UI components from page-level views.

Implementation resides in `services/frontend/`.

## Data Flow

The complete data flow from device discovery to cloud storage follows a well-defined pipeline that enforces the privacy boundary at every step.

## Sanitization Pipeline

When the Agent discovers devices and collects configurations, the sanitization pipeline transforms raw data into safe-for-upload artifacts through three progressive stages.

The first stage receives raw configurations from the collector. If a TextFSM template exists for the detected device type, Tier 1 applies template-based parsing to precisely identify and redact sensitive fields. If no template exists, this tier passes through unchanged.

The second stage applies section-aware regex patterns. The TierResolver determines that configuration has recognizable structure (interface declarations, router blocks, etc.) and Tier 2 applies patterns specific to each section type. For example, within interface sections, IP addresses are redacted; within username sections, passwords and secrets are redacted.

The third stage applies aggressive catch-all patterns to catch anything missed by the first two tiers. This ensures complete sanitization even for unknown device types or unusual configuration syntax.

After all three tiers complete, the sanitizer outputs the fully redacted configuration text, a list of all redactions made (with hashes, not original values), and metadata about which tiers were applied.

The vectorizer then generates embeddings from the sanitized text, and the uploader transmits everything to the API.

## API Data Flow

The API receives upload requests from agents and processes them through several steps. Device metadata is validated and stored in PostgreSQL. Vector embeddings are stored with pgvector indexing for similarity search. Topology relationships are stored in Neo4j as graph nodes and edges. Audit logs record the upload event.

The frontend queries data through the API. Devices are fetched from PostgreSQL. Topology visualization queries Neo4j. Semantic searches query pgvector for similar configurations.

## Security Architecture

Security operates at multiple layers to protect data in transit and at rest.

All communication between Agent and API uses HTTPS with TLS 1.3. The Agent authenticates using JWT tokens issued during agent registration. The API validates tokens on every request.

Credentials stored in PostgreSQL use Fernet symmetric encryption via the EncryptedText type decorator. The encryption key comes from environment configuration and must be set during deployment.

API authentication uses JWT-based session management. Endpoints require valid tokens, and role-based access control restricts operations based on user permissions.

## Deployment Architecture

The platform deploys using Docker Compose for local development and Kubernetes for production. Both orchestration systems define the same services with production-grade configuration for the latter.

The Docker Compose setup defines services for PostgreSQL with pgvector, Redis for caching and task queues, Vault for secrets management, Ollama for local LLM processing, the FastAPI application, the React frontend, and the Agent container.

Each service maintains configuration through environment variables with sensible defaults. Production deployments override defaults with secure values.

## Scaling Considerations

The architecture supports horizontal scaling at multiple layers. Multiple Agent instances can run in parallel, each handling different network segments. The API service can scale horizontally behind a load balancer. PostgreSQL can scale with read replicas for query-heavy workloads. Neo4j supports causal clusters for high availability.

The separation of concerns between vector storage, graph storage, and relational storage enables independent scaling of each data type based on workload characteristics.

## Technology Choices

Several architectural decisions shaped the technology stack.

Python async for the Agent enables efficient concurrent device polling. FastAPI for the API provides high-performance async request handling. PostgreSQL with pgvector eliminates the need for separate vector databases. Neo4j handles graph workloads that relational databases cannot efficiently process. Docker containers enable consistent deployment across environments. Chakra UI provides accessible, themeable frontend components.

These choices prioritize reliability, privacy, and operational simplicity over raw performance metrics.