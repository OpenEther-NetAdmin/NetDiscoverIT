# Security and Privacy

NetDiscoverIT implements a privacy-first architecture that ensures sensitive network configuration data never leaves the customer network. This document details the security measures and privacy guarantees.

## Privacy Guarantee

**Raw device configurations never leave the customer network.** This is not a policy that can be bypassed—it is architecturally enforced. The agent's sanitizer module strips all passwords, secrets, API keys, community strings, and other sensitive data before any upload.

Only the following data is transmitted to the cloud:

- Sanitized device metadata (hostname, IP addresses, vendor, model)
- Topology relationships (device connections without credentials)
- Vector embeddings (for semantic search)
- Redaction logs (with hashed values, not actual secrets)

## Sanitization Pipeline

The sanitizer implements a three-tier approach for comprehensive coverage:

### Tier 1: TextFSM Templates

When a device type is recognized and a TextFSM template exists, the sanitizer uses template-based parsing. This provides precise identification and redaction of fields based on the template's field definitions.

### Tier 2: Section-Aware Regex

For configurations with recognizable section structure (interface blocks, router processes, etc.), the sanitizer applies targeted regex patterns based on the section context. This catches sensitive data within specific configuration sections.

### Tier 3: Aggressive Catch-All

A final tier of aggressive regex patterns catches any remaining sensitive data that the first two tiers missed. This ensures complete sanitization even for unknown device types.

## Redaction Logging

The sanitizer produces a redaction log that accompanies uploaded data. This log enables audit and compliance tracking without storing actual secrets.

Each redaction entry includes:

- Data type (e.g., password, secret, ipv4)
- Line number where redaction occurred
- Hash of original value (SHA-256, truncated to 16 characters)
- Token replacement used
- Tier that performed the redaction

The hash enables verification that a specific value was redacted without storing the value itself.

## Encryption at Rest

Credentials stored in the API database use Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256). The `EncryptedText` SQLAlchemy type decorator handles encryption and decryption transparently.

Encryption keys come from the `CREDENTIAL_ENCRYPTION_KEY` environment variable. This key must be set during deployment and should be stored securely.

## Authentication and Authorization

### Agent Authentication

Agents authenticate to the API using JWT tokens. Tokens are issued during agent registration and include claims for organization and agent identity.

```http
Authorization: Bearer <jwt_token>
```

### User Authentication

API users authenticate via JWT tokens. Tokens include claims for user identity, organization, and role.

### Role-Based Access Control

Users have roles that determine their access:

- **Admin**: Full access to all resources
- **Editor**: Can create and modify resources
- **Viewer**: Read-only access

## Network Security

### TLS Encryption

All communication between agent and API uses HTTPS with TLS 1.3. The API service terminates TLS and handles internal communication over the Docker network.

### Network Isolation

The agent runs within the customer's network segment. It cannot access external networks beyond what the local network allows. The API service is reachable only through defined endpoints.

## Secrets Management

### Environment Variables

Required secrets are provided through environment variables. The application fails to start if critical secrets are unset.

### HashiCorp Vault

For production deployments, HashiCorp Vault manages secrets. The API service integrates with Vault for dynamic credential retrieval.

## Compliance Considerations

The privacy architecture supports compliance with various regulations:

### GDPR

- Data minimization: Only sanitized metadata is stored
- Encryption: Credentials are encrypted at rest
- Audit trails: Redaction logs provide visibility

### PCI DSS

- Network segmentation: Agent runs in customer network
- Encryption: Data encrypted in transit and at rest
- Access control: Role-based access to API

### Data Sovereignty

- Local processing: All config processing happens on-premises
- No raw data transfer: Only sanitized data leaves the network
- Regional storage: Data stored where customer specifies

## Security Best Practices

1. **Rotate secrets regularly** - Implement a schedule for key rotation
2. **Use strong passwords** - Enforce password complexity for credentials
3. **Enable audit logging** - Track all access and modifications
4. **Monitor for anomalies** - Set up alerts for unusual activity
5. **Keep software updated** - Apply security patches promptly