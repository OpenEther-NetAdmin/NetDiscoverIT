# NetDiscoverIT Overview

NetDiscoverIT is a network discovery and topology mapping platform with a privacy-first architecture. The platform enables organizations to discover network devices, collect configurations, map topology relationships, and generate vector embeddings for semantic search—all while ensuring sensitive credential data never leaves the customer network.

## What NetDiscoverIT Does

The platform addresses a critical challenge in network management: understanding what devices exist on your network and how they connect, without exposing sensitive configuration data to cloud services. NetDiscoverIT solves this through a local agent architecture that sanitizes all data before any information leaves the customer premises.

Key capabilities include automated discovery of network devices through SSH, SNMP, and Nmap protocols, configuration collection from routers, switches, and firewalls, topology mapping using CDP/LLDP neighbor relationships, semantic search powered by vector embeddings, and change detection to identify configuration drift.

## Core Architecture

The platform consists of three main components that work together to provide a complete network discovery solution.

The Agent Service runs on-premises within the customer's network as a Docker container. It handles all device interactions, configuration collection, and—most critically—data sanitization before any upload. The agent never sends raw configurations, passwords, or secrets to the cloud.

The API Service provides the backend for data storage, serving as the interface between agents and the cloud platform. It exposes REST endpoints for device management, topology queries, and discovery operations. The API stores sanitized metadata in PostgreSQL and topology relationships in Neo4j.

The Frontend delivers the user interface for visualizing discovered devices, exploring topology graphs, and managing the platform. It connects to the API service and provides operators with actionable insights into their network infrastructure.

## Privacy Guarantee

The fundamental principle governing NetDiscoverIT's design is that raw device configurations never leave the customer network. This is not a policy that can be bypassed—it is architecturally enforced. The agent's sanitizer module strips all passwords, secrets, API keys, community strings, and other sensitive data before uploading metadata to the cloud. Only sanitized configurations, topology relationships, and vector embeddings are transmitted.

This architecture ensures compliance with data sovereignty requirements and provides peace of mind for organizations handling sensitive network infrastructure.

## Technology Stack

The platform leverages modern, proven technologies to deliver reliable network discovery capabilities.

The agent service uses Python with async support for efficient concurrent operations. It integrates with established network libraries including NetMiko for SSH connectivity, NAPalm for multi-vendor support, and IVRE for advanced network reconnaissance. The sanitizer employs a tiered approach using TextFSM templates, section-aware regex patterns, and aggressive catch-all patterns.

The API service runs on FastAPI, taking advantage of Python's async ecosystem for high-performance request handling. PostgreSQL with the pgvector extension provides both relational data storage and vector embeddings for semantic search capabilities. Neo4j handles the graph-based topology data, enabling complex relationship queries.

The frontend uses React 19 with Chakra UI v3 for the component library and React Query for server state management. This modern stack delivers a responsive, accessible user experience.

## Current Status

Phase 1 establishes the foundational architecture and core sanitization pipeline. The agent can discover devices, collect configurations, sanitize sensitive data through three tiers of processing, generate vector embeddings, and upload sanitized metadata to the API. The API can store device records, vector embeddings, and topology relationships. The frontend provides basic visualization of discovered devices.

Phase 2 will expand capabilities to include enhanced scanning modes, more sophisticated topology mapping, integration with external ticketing systems, and advanced alerting for configuration changes.

## Repository Structure

The repository organizes code by service component to keep related functionality together and enable independent development and deployment of each layer.

The `services/agent/` directory contains all code running on the customer premises. This includes the scanner for network discovery, collector for configuration retrieval, sanitizer for data scrubbing, topology for relationship mapping, vectorizer for embedding generation, and uploader for cloud communication.

The `services/api/` directory holds the FastAPI application, database models, API routes, background tasks, and Alembic migrations for schema management.

The `services/frontend/` directory contains the React application with components, pages, and styling.

The `docs/` directory includes architecture diagrams, style guides, and implementation plans.

## Getting Started

To begin using NetDiscoverIT, ensure Docker is installed and running on your system. Copy the example environment file and adjust settings as needed for your deployment. Use Docker Compose to start all services: the API runs on port 8000, the frontend on port 3000, and supporting services like PostgreSQL, Redis, and Neo4j on their respective ports.

Detailed instructions for configuration, deployment, and usage are available in the subsequent sections of this documentation.