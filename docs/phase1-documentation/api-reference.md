# API Reference

The API service provides REST endpoints for agent communication, frontend queries, and administrative operations. This document covers the main endpoints and their usage.

## Base URL

All API endpoints are prefixed with `/api/v1`:

```
http://localhost:8000/api/v1
```

## Authentication

The API uses JWT-based authentication. Include the token in the Authorization header:

```
Authorization: Bearer <token>
```

## Endpoints

### Health Check

**GET** `/health`

Returns the health status of the API service.

**Response:**

```json
{
  "status": "healthy"
}
```

### Devices

**GET** `/devices`

List all devices for the authenticated user's organization.

**Query parameters:**

- `skip` (int): Number of records to skip
- `limit` (int): Maximum number of records to return
- `organization_id` (str): Filter by organization

**Response:**

```json
[
  {
    "id": "uuid",
    "hostname": "router-01",
    "management_ip": "10.1.1.1",
    "vendor": "Cisco",
    "device_type": "router",
    "role": "core",
    "organization_id": "uuid",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z"
  }
]
```

**GET** `/devices/{device_id}`

Get a specific device by ID.

**POST** `/devices`

Create a new device record.

**PUT** `/devices/{device_id}`

Update an existing device.

**DELETE** `/devices/{device_id}`

Delete a device.

### Discoveries

**GET** `/discoveries`

List discovery runs.

**POST** `/discoveries`

Create a new discovery run.

**GET** `/discoveries/{discovery_id}`

Get a specific discovery run.

### Scans

**GET** `/scans`

List scan records.

**POST** `/scans`

Create a new scan record.

### Topology

**GET** `/topology`

Get topology graph data.

**Query parameters:**

- `device_id` (str): Filter by root device

### Agents

**GET** `/agents`

List registered agents.

**POST** `/agents`

Register a new agent.

**GET** `/agents/{agent_id}`

Get agent details.

**PUT** `/agents/{agent_id}`

Update agent configuration.

### Alerts

**GET** `/alerts`

List alerts.

**POST** `/alerts`

Create an alert rule.

**PUT** `/alerts/{alert_id}`

Update an alert rule.

**DELETE** `/alerts/{alert_id}`

Delete an alert rule.

### Audit Logs

**GET** `/audit-logs`

List audit log entries.

**Query parameters:**

- `resource_type` (str): Filter by resource type
- `action` (str): Filter by action

## Error Responses

The API returns standard HTTP status codes:

- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `500` - Internal Server Error

Error responses include details:

```json
{
  "detail": "Error message description"
}
```

## Rate Limiting

Rate limiting is enforced at the API gateway level. Specific limits depend on subscription tier.