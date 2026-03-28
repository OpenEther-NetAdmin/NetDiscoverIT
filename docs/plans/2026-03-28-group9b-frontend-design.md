# Group 9b Frontend — Topology Map, Compliance Viewer, NLI Chat

**Goal:** Deliver three new frontend pages — a D3 full-network topology map, a two-tab compliance report viewer, and a scrollable NLI chat assistant — consuming existing backend APIs with one new topology HTTP endpoint.

**Architecture:** Feature-folder pattern under `src/pages/`, matching the established `src/pages/changes/` convention. Three new routes added to `App.js` and Sidebar. One new backend route (`GET /api/v1/topology`) wraps the existing `neo4j.get_topology()` method. New dependencies: `d3` (topology SVG), `react-markdown` (NLI answer rendering).

**Tech Stack:** React 18, Chakra UI v2, React Router v6, D3 v7, react-markdown, Jest + RTL, existing `api.js` service pattern.

---

## Architecture Overview

### New routes

| Route | Component | Sidebar label |
|---|---|---|
| `/topology` | `src/pages/topology/TopologyMap.jsx` | Network Map |
| `/compliance` | `src/pages/compliance/ComplianceViewer.jsx` | Compliance |
| `/assistant` | `src/pages/assistant/AssistantPage.jsx` | Assistant |

The existing `/path-visualizer` route and `PathVisualizer.jsx` are untouched.

### File structure

```
src/pages/topology/
  TopologyMap.jsx        — page root: filter bar + D3 SVG canvas
  useTopology.js         — custom hook: fetch, transform, expose filtered data
  topologyUtils.js       — node shape/color helpers, legend config constant

src/pages/compliance/
  ComplianceViewer.jsx   — page root: Chakra Tabs wrapper
  GenerateTab.jsx        — framework picker, date range, format select, submit
  HistoryTab.jsx         — report list table, live status badges, download
  useReportPolling.js    — custom hook: poll one report until terminal status
  complianceUtils.js     — FRAMEWORKS array, STATUS_COLORS, FORMAT_LABELS

src/pages/assistant/
  AssistantPage.jsx      — page root: message list + fixed input bar
  ChatMessage.jsx        — single message bubble (user or AI with markdown)
  SourceCard.jsx         — device chip with similarity score, links to /devices/:id
  assistantUtils.js      — QUERY_TYPE_COLORS, confidenceColor(score)
```

### New backend endpoint

```
GET /api/v1/topology
Auth: Bearer JWT (standard get_current_user dependency)
Response 200:
  {
    "nodes": [
      {
        "id": "uuid",
        "type": "device",
        "hostname": "RTR-CORE-1",
        "device_type": "router",          // router | switch | firewall | server | unknown
        "management_ip": "10.0.0.1",
        "compliance_scope": ["PCI-CDE"],
        "organization_id": "uuid"
      }
    ],
    "edges": [
      { "source": "device-uuid-1", "target": "device-uuid-2", "vlan_id": 10 }
    ],
    "node_count": 12,
    "edge_count": 18
  }
Response 503: { "detail": "Topology unavailable: Neo4j not connected" }
Response 401: unauthenticated
```

Neo4j returns interface-level edges (`Interface CONNECTED_TO Interface`). The route collapses these to device-level edges (deduplicated) so the graph shows device-to-device links. The `neo4j.get_topology(org_id)` method at `db/neo4j.py:325` already returns the raw data; the new route normalizes it.

New route file: `services/api/app/api/routes/topology.py`
Registered in: `services/api/app/api/routes/__init__.py` with `prefix="/topology"`

### api.js additions

```js
getTopology()
  // GET /api/v1/topology

createComplianceReport({ framework, format, period_start, period_end, scope_override })
  // POST /api/v1/compliance/reports

getComplianceReport(id)
  // GET /api/v1/compliance/reports/{id}

listComplianceReports({ status, framework, skip = 0, limit = 20 } = {})
  // GET /api/v1/compliance/reports?status=&framework=&skip=&limit=

queryAssistant({ question, top_k = 5 })
  // POST /api/v1/query
```

---

## Feature 1 — Topology Map (`/topology`)

### Data flow

`useTopology` hook calls `api.getTopology()` on mount. It stores raw nodes/edges and derives filtered arrays based on active filter state (hostname search string, compliance scope selection). The hook returns `{ nodes, edges, loading, error, reload }` — the filtered arrays are passed directly into the D3 effect.

### D3 integration

React owns the `<svg ref={svgRef}>` element and all state above it (filters, selected node ID). D3 runs exclusively inside a `useEffect` that:
1. Clears the SVG on each run
2. Creates a force simulation: `forceLink` (edge lengths), `forceManyBody` (repulsion), `forceCenter`
3. Renders edges as `<line>` elements, nodes as `<g>` groups
4. Attaches drag behaviour and zoom/pan to the SVG

D3 does **not** call React state setters during simulation ticks (avoids re-render loops). Click on a node calls a React state setter (`setSelectedNodeId`) which triggers a Chakra Popover via a separate React-controlled overlay.

### Node visual design

Shape by `device_type`:

| device_type | SVG shape | Fill color |
|---|---|---|
| `router` | circle r=18 | `#3182CE` (blue) |
| `switch` | rect 32×32 | `#718096` (gray) |
| `firewall` | diamond (rotated rect 24×24) | `#E53E3E` (red) |
| `server` | rect 36×20 | `#38A169` (green) |
| `unknown` | circle r=16 | `#A0AEC0` (light gray) |

Compliance scope badge: small filled circle `r=6` offset `(+14, -14)` from node center.

| Scope tag (first match) | Badge color |
|---|---|
| `PCI-CDE` or `PCI-BOUNDARY` | `#DD6B20` orange |
| `HIPAA-PHI` | `#6B46C1` purple |
| `SOX-FINANCIAL` | `#D69E2E` yellow |
| `FEDRAMP-BOUNDARY` | `#C53030` dark red |
| `ISO27001` or `SOC2` or `NIST-CSF` | `#2B6CB0` steel blue |
| None | no badge rendered |

Hostname label: `<text>` centered below node, truncated to 12 chars with `…`.

### Filter bar (above canvas)

- Text input: filters nodes whose `hostname` contains the search string (case-insensitive). Non-matching nodes and their incident edges are removed from the simulation data.
- Compliance scope `<Select>`: "All scopes" or one specific scope tag. Filters nodes to those whose `compliance_scope` array contains the selected tag.
- Refresh button: calls `useTopology`'s `reload()` to re-fetch from API.

### Node detail popover

Clicking a node sets `selectedNodeId`. A Chakra `Popover` (positioned near the click using a fixed offset, not attached to the SVG element) renders:
- Hostname (bold), management IP, device type badge, vendor if present
- Compliance scope tags (orange/purple Tag components)
- "View Device" button → `navigate('/devices')` (filters by ID — existing Devices page handles this)

Clicking elsewhere on the canvas clears `selectedNodeId` and closes the popover.

### Legend

Fixed HTML overlay in bottom-left corner of the canvas (absolute positioned div, not SVG). Shows shape=device type and dot color=compliance scope in two small groups.

### Loading / error / empty states

- Loading: `<Spinner>` centered in the canvas area
- Error: red text + "Retry" button calling `reload()`
- Empty (0 nodes returned): centered message "No devices found. Run a discovery to populate your network map."

---

## Feature 2 — Compliance Report Viewer (`/compliance`)

### Page structure

```jsx
<ComplianceViewer>
  <Tabs index={tabIndex} onChange={setTabIndex}>
    <TabList>
      <Tab>Generate</Tab>
      <Tab>History</Tab>
    </TabList>
    <TabPanels>
      <TabPanel><GenerateTab onCreated={handleCreated} /></TabPanel>
      <TabPanel><HistoryTab triggerReload={reloadFlag} /></TabPanel>
    </TabPanels>
  </Tabs>
</ComplianceViewer>
```

`handleCreated(reportId)` sets `tabIndex` to 1 (History tab) and flips `reloadFlag` (a counter) so `HistoryTab` re-fetches its list. `ComplianceViewer` controls tab switching via Chakra's controlled `Tabs` (`index` + `onChange` props).

### GenerateTab

**Framework picker:** Seven pill buttons (Chakra `Button` with `variant="outline"` / `variant="solid"` toggle). Only one active at a time. Required — submit disabled until one is selected.

```
FRAMEWORKS = [
  { id: 'pci_dss',   label: 'PCI-DSS v4.0', color: 'red' },
  { id: 'hipaa',     label: 'HIPAA',         color: 'purple' },
  { id: 'sox_itgc',  label: 'SOX ITGC',      color: 'yellow' },
  { id: 'iso_27001', label: 'ISO 27001',      color: 'blue' },
  { id: 'nist_csf',  label: 'NIST CSF',      color: 'cyan' },
  { id: 'fedramp',   label: 'FedRAMP',        color: 'green' },
  { id: 'soc2',      label: 'SOC 2',          color: 'teal' },
]
```

**Date range:** Two `<Input type="date">` fields. Defaults: start = today minus 365 days, end = today. Client validation: end must be after start (inline error, submit stays disabled).

**Format:** Chakra `<Select>` with options: PDF, DOCX, Both.

**Submit:** Calls `api.createComplianceReport(...)`. On success: success toast "Report generation started", calls `onCreated(report.id)`. On error: error toast with API message.

### HistoryTab

On mount: calls `api.listComplianceReports()` to populate the table.

**Table columns:** Framework · Format · Period · Status · Started · Action

**Status badge colors** (from `complianceUtils.STATUS_COLORS`):

| status | Badge | Color |
|---|---|---|
| `pending` | Spinner + "Pending" | yellow |
| `generating` | Spinner + "Generating" | yellow |
| `completed` | "Ready" | green |
| `failed` | "Failed" | red |

**Action column:**
- `completed`: "Download" button → calls `api.getComplianceReport(id)` to get a fresh presigned URL → opens in new tab (`window.open`)
- `failed`: "Retry" button → submits same parameters again via `api.createComplianceReport`
- `pending`/`generating`: disabled "Pending..." text

**Polling (`useReportPolling.js`):**

```js
function useReportPolling(reports, onUpdate) {
  // Runs a setInterval (3000ms) while any report in `reports` has
  // status 'pending' or 'generating'.
  // On each tick: calls api.listComplianceReports() and passes the
  // refreshed list to onUpdate(). Clears the interval when all
  // reports reach terminal status or on unmount.
}
```

`HistoryTab` passes its full reports array into this hook. When a report reaches `completed` or `failed`, `onUpdate` replaces the corresponding entry in local state (the interval auto-stops once nothing is pending).

---

## Feature 3 — NLI Chat Assistant (`/assistant`)

### Page layout

```
┌─────────────────────────────────────┐
│  Heading: "Network Assistant"       │
│  Subtitle: "Ask anything about..."  │
├─────────────────────────────────────┤
│                                     │
│  [scrollable message history]       │
│  flex-grow, overflow-y: auto        │
│                                     │
├─────────────────────────────────────┤
│  [Textarea input]     [Send button] │
└─────────────────────────────────────┘
```

The outer container uses `h="100%"` — the parent `<Box flex="1" overflow="auto">` in `App.js` already constrains height to the viewport. Message area is `flex="1"` with `overflowY="auto"`. Input bar is `flexShrink={0}` at the bottom.

### Message state

```js
const [messages, setMessages] = useState([]);
// Each message:
// { id: crypto.randomUUID(), role: 'user', text: '...' }
// { id: crypto.randomUUID(), role: 'assistant', answer, sources, confidence,
//   query_type, retrieved_device_count, graph_traversal_used }
// { id: crypto.randomUUID(), role: 'error', text: '...' }     // API failures
```

On send:
1. Append user message to state
2. Clear textarea
3. Set `isLoading = true` (disables send, shows spinner)
4. Call `api.queryAssistant({ question, top_k: 5 })`
5. On success: append assistant message
6. On error: append error message (role: 'error')
7. Set `isLoading = false`
8. Scroll to bottom via `messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })`

No message is editable or deleteable. No persistence — state resets on page navigation. A "Clear conversation" button in the page header resets `messages` to `[]`.

### ChatMessage.jsx

**User bubble:** right-aligned, `bg="blue.500"` text in white, `borderRadius="lg"`, max-width 70%.

**Assistant card:** left-aligned, white card with border, full width.
- Top-right: `query_type` badge using `QUERY_TYPE_COLORS`
- Answer: `<ReactMarkdown>` (components override: `p` → Chakra `Text`, `li` → Chakra `ListItem`, `strong` → bold span). Prose from Claude may include bullet lists, bold terms, short headings.
- Confidence row: thin `<Progress>` bar (Chakra) + `{Math.round(confidence * 100)}%` label. Color: `green` ≥0.8, `yellow` ≥0.5, `red` <0.5.
- Graph traversal indicator: small `FiGitBranch` icon + "Graph used" text if `graph_traversal_used: true`.
- Source chips: `<Wrap>` of `<SourceCard>` components.

**Error message:** centered red text with warning icon — "Could not answer: [message]".

### SourceCard.jsx

```jsx
<Tag
  as={Link}
  to={`/devices`}    // navigates to devices page (no per-device route yet)
  size="sm"
  colorScheme="blue"
  variant="subtle"
  cursor="pointer"
>
  <TagLabel>{hostname} · {Math.round(similarity * 100)}%</TagLabel>
</Tag>
```

### assistantUtils.js

```js
export const QUERY_TYPE_COLORS = {
  topology:   'blue',
  security:   'red',
  compliance: 'orange',
  changes:    'purple',
  inventory:  'gray',
};

export function confidenceColor(score) {
  if (score >= 0.8) return 'green';
  if (score >= 0.5) return 'yellow';
  return 'red';
}
```

### Input bar behaviour

- Chakra `<Textarea>` with `rows={1}` and `resize="none"` — grows up to 3 rows via CSS `max-height`.
- `onKeyDown`: Enter (without Shift) calls `handleSend()`; Shift+Enter inserts newline.
- Send button disabled when `isLoading` or `question.trim() === ''`.
- While loading: send button shows `<Spinner size="sm">` instead of send icon.

---

## Sidebar Updates

`src/components/Sidebar.jsx` gets two new `NavItem` entries:

```jsx
<NavItem to="/topology"    icon={FiGlobe}>Network Map</NavItem>
<NavItem to="/compliance"  icon={FiShield}>Compliance</NavItem>
<NavItem to="/assistant"   icon={FiMessageSquare}>Assistant</NavItem>
```

Inserted between "Changes" and "Path Visualizer" (which stays). Icons from `react-icons/fi` (already installed).

---

## Testing

### Unit tests

**`src/__tests__/TopologyMap.test.jsx`**
- Renders spinner while `api.getTopology` is in-flight
- Renders SVG container once data resolves
- Hostname search filter: non-matching nodes removed from `useTopology` filtered output
- Compliance scope filter: only matching nodes remain
- Error state renders "Retry" button; clicking it calls `api.getTopology` again

**`src/__tests__/ComplianceViewer.test.jsx`**
- Framework pill: clicking one activates it, clicking another deactivates the first
- Submit disabled until framework selected
- Date validation: end before start shows inline error, blocks submit
- Successful submit: calls `api.createComplianceReport` with correct params, switches to History tab
- History tab: renders rows with correct status badges
- Completed row shows "Download" button; pending row shows spinner
- `useReportPolling` stops polling when status reaches `completed`

**`src/__tests__/AssistantPage.test.jsx`**
- User message appears in thread after submit
- Textarea cleared after submit
- Send button disabled while loading
- Assistant response: answer text present, source chips present, confidence bar present
- Error response renders red error message
- Enter key submits; Shift+Enter does not submit
- "Clear conversation" button empties message list

### Integration test

**`src/__tests__/integration/TopologyCompliance.test.jsx`**
- Generate report → toast appears → History tab shown → pending row present → polling resolves → "Download" button appears

### Backend unit test

**`tests/api/test_topology.py`**
- `GET /api/v1/topology` with valid auth → 200, nodes/edges/node_count/edge_count present
- Interface-level edges collapsed to device-level (no duplicate device pairs)
- Unauthenticated → 401
- Neo4j client raises `RuntimeError` → 503

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `getTopology` fails | Error state in canvas; retry button |
| Neo4j not connected | API returns 503; frontend shows same error state |
| `createComplianceReport` fails | Error toast with API message; form stays open |
| Report generation fails (`status: failed`) | Red badge in history; "Retry" button |
| `queryAssistant` fails | Red error message appended to chat thread |
| NLI service unavailable (503) | Error message: "AI assistant is temporarily unavailable" |
| `react-markdown` receives null/undefined | Guarded: render plain text if answer is falsy |

---

## Dependencies

```
npm install d3 react-markdown
```

`d3` v7 — force simulation, zoom, drag. MIT.
`react-markdown` v9 — markdown rendering with component overrides. MIT.

Both are well-maintained and have no peer dependency conflicts with React 18 + Chakra UI v2.
