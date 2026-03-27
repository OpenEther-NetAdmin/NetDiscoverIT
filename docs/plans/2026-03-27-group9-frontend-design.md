# Group 9 — Frontend Phase 2 Design
## Change Management UI + MSP Org Switcher

**Created:** 2026-03-27
**Status:** Approved — ready for implementation
**Scope:** Group 9, items 1 and 2 from phase2-work-plan.md

---

## Overview

Two features added to the existing React frontend (Chakra UI, functional components, hooks):

1. **Change Management UI** — browse, filter, and action ChangeRecord entities through their full lifecycle
2. **MSP Org Switcher** — MSP users can switch the active org context from the sidebar; all pages update accordingly

Both features share a new `OrgContext` that provides the active org ID to the whole app.

---

## Architecture

### Approach

Feature-folder structure + `OrgContext`. Extends the existing `AuthContext` pattern. All API calls remain in the `api.js` singleton. No new dependencies introduced.

### Component Structure

```
services/frontend/src/
  context/
    AuthContext.js          (existing — unchanged)
    OrgContext.js           (NEW)

  pages/
    Dashboard.jsx           (existing — updated to consume OrgContext)
    changes/
      ChangeList.jsx        (rich card list + filter bar)
      ChangeDrawer.jsx      (slide-over drawer with expand-to-full)
      ChangeDetail.jsx      (detail body — shared by drawer and full-page route)
    Settings.jsx            (existing — unchanged)
    Devices.jsx             (existing — unchanged)
    Discoveries.jsx         (existing — unchanged)
    PathVisualizer.jsx      (existing — unchanged)

  components/
    Sidebar.jsx             (existing — add org switcher block below logo)

  services/
    api.js                  (existing — add change + MSP methods)
```

### Routes

Added to `App.js`:

| Path | Component | Notes |
|------|-----------|-------|
| `/changes` | `ChangeList` | Main list view |
| `/changes/:id` | `ChangeDetail` | Deep-linkable full-page view |

`ChangeDrawer` is rendered inside `ChangeList` (not a route). The drawer overlays the list; clicking **Expand** navigates to `/changes/:id`.

---

## OrgContext

Wraps the whole app inside `AuthProvider`. Provides:

```js
{
  activeOrg: { id, name, is_msp },  // currently viewed org
  managedOrgs: [...],               // populated for MSP users via GET /api/v1/msp/overview
  isMsp: bool,
  switchOrg: (orgId) => void,       // updates activeOrg, triggers refetch across pages
}
```

On mount, `OrgContext` calls `getMspOverview()`. If it succeeds, `isMsp=true` and `managedOrgs` is populated. If it fails (non-MSP user or network error), `isMsp=false` and `managedOrgs=[]` — the switcher never renders.

`api.js` exposes `api.setActiveOrg(id)`. `OrgContext` calls this on init and on every `switchOrg()`. All subsequent API requests inject `X-Org-Id: <activeOrg.id>` in the request headers.

Pages that load org-scoped data (Dashboard, ChangeList, Devices) re-run their data load when `activeOrg` changes — they subscribe to `OrgContext` via `useContext`.

---

## MSP Org Switcher (Sidebar)

Rendered inside `Sidebar.jsx` only when `isMsp === true`. Placed immediately below the "NetDiscoverIT" logo block.

Appearance:
- Labelled `ORG` in small uppercase
- Shows `activeOrg.name` with a chevron
- Click opens a Chakra `Menu` listing all `managedOrgs`
- Selecting an org calls `switchOrg(org.id)`

Non-MSP users: the block is not rendered. `OrgContext` exists but is a no-op for them.

---

## Change Management UI

### ChangeList

- Loads `GET /api/v1/changes` on mount and on `activeOrg` change
- **Filter bar:** status dropdown (all / draft / proposed / approved / implemented / verified / rolled_back), risk level dropdown (all / low / medium / high / critical), text search on title and change number
- Each card displays:
  - Change number (CHG-YYYY-NNNN) · title · status badge · risk badge
  - Affected device count · compliance scope tags
  - Simulation status icon (✅ passed / ⚠️ not run) if `simulation_performed=true`
  - External ticket link if `external_ticket_url` is set
  - Contextual action button (role-aware — see Role Guards below)
- Clicking anywhere on a card (except the action button) opens `ChangeDrawer`

### ChangeDrawer

- Chakra `Drawer` with `size="lg"` (wide slide-over from the right)
- Header: change number, status badge, close (✕) button, expand icon (⤢)
- Expand button navigates to `/changes/:id`
- Body: renders `ChangeDetail` component
- Backdrop dims the list; list stays mounted

### ChangeDetail

Used inside `ChangeDrawer` and at the `/changes/:id` full-page route. Renders the same sections in both contexts. In full-page mode the expand button is not shown.

**Sections:**

1. **Lifecycle stepper** — horizontal progress showing Draft → Proposed → Approved → Implemented → Verified. Completed steps green, current step highlighted, future steps grey.
2. **Metadata** — description, change type, risk level, requested by/at, scheduled window
3. **Affected devices** — tag list of device hostnames
4. **Compliance scopes** — tag list (PCI-CDE, SOX-FINANCIAL, etc.)
5. **Simulation** — pass/fail badge; collapsible JSON results if `simulation_performed=true`
6. **External ticket** — clickable link to ServiceNow/JIRA if `external_ticket_url` is present
7. **Evidence** — pre/post config hashes, implementation evidence, verification results (fields populate as the record moves through lifecycle)
8. **Action button** — role-aware, full-width, pinned to bottom of drawer / bottom of page

### Role Guards

Action buttons are only rendered when the current user has permission to perform that transition. Non-permitted buttons are not shown — no disabled state, no lock icons.

| Status | Permitted role | Button shown |
|--------|---------------|--------------|
| `draft` | engineer, admin | Propose |
| `proposed` | admin | Approve |
| `approved` | engineer, admin | Implement |
| `implemented` | admin | Verify |
| any | admin | Rollback (secondary/destructive style) |

Role is read from `AuthContext` (`user.role`). The check is client-side only (the backend enforces it server-side on the actual transition call).

### State Transition UX

Clicking an action button (Propose, Approve, etc.) calls the corresponding API method. On success:
- Re-fetch the change record and update the card/stepper with the fresh data
- A Chakra success toast confirms the transition

On failure (400 invalid transition, 403 role, 400 simulation not passed):
- A Chakra error toast with the backend's `detail` message
- The drawer/card stays open — no navigation

---

## API Service Layer

New methods added to the `ApiService` class in `api.js`:

```js
// Org context
setActiveOrg(orgId)                            // sets X-Org-Id header for all requests

// Changes
getChanges(filters = {})                       // GET /api/v1/changes
getChange(id)                                  // GET /api/v1/changes/{id}
createChange(data)                             // POST /api/v1/changes
updateChange(id, data)                         // PATCH /api/v1/changes/{id}
deleteChange(id)                               // DELETE /api/v1/changes/{id}
proposeChange(id)                              // POST /api/v1/changes/{id}/propose
approveChange(id, { notes })                   // POST /api/v1/changes/{id}/approve
implementChange(id, { implementation_evidence })// POST /api/v1/changes/{id}/implement
verifyChange(id, { verification_results })     // POST /api/v1/changes/{id}/verify
rollbackChange(id, { rollback_evidence })      // POST /api/v1/changes/{id}/rollback

// MSP
getMspOverview()                               // GET /api/v1/msp/overview
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| List load failure | Inline error message + Retry button (matches Devices.jsx pattern) |
| State transition 400/403 | Chakra error toast; drawer stays open |
| `getMspOverview()` failure | `managedOrgs=[]`; switcher hidden; graceful degradation |
| Network error on detail load | Error state with Retry inside drawer/full-page |

---

## Testing Strategy

### Unit Tests (Jest + React Testing Library)

- **`ChangeList`** — renders cards from mocked API; filter bar correctly filters by status and risk; action button visibility per role (engineer: Propose visible, Approve hidden; viewer: no buttons)
- **`ChangeDetail`** — lifecycle stepper highlights correct step per status; all 5 lifecycle sections render; expand button present in drawer mode, absent in full-page
- **`ChangeDrawer`** — opens on card click; closes on backdrop / X; navigates to `/changes/:id` on expand
- **`OrgContext`** — `switchOrg()` updates `activeOrg`; `isMsp` false when `managedOrgs` empty; list populated from `getMspOverview()` response
- **`Sidebar`** — org switcher block renders when `isMsp=true`; hidden when `isMsp=false`

### Integration Tests (MSW mock service worker)

- **Full lifecycle flow** — list loads → click card → drawer opens → Propose → card status badge updates to `proposed`
- **Role guard** — login as viewer → no action buttons on any card
- **MSP org switch** — switch org → change list reloads with correct `X-Org-Id` header
- **Drawer expand** — click expand → navigate to `/changes/:id` → `ChangeDetail` renders same data as drawer

---

## Sidebar Nav Updates

One new nav item added to `Sidebar.jsx`:

| Icon | Label | Route |
|------|-------|-------|
| `FiClipboard` | Changes | `/changes` |

MSP org switcher block positioned between the logo block and the nav items (only visible to MSP users).

---

## Dependencies

- No new npm packages required
- Backend endpoints already implemented (Group 2 + Group 4): `/api/v1/changes/*`, `/api/v1/msp/overview`
- **`AuthContext` role gap (must fix in implementation):** `AuthContext` currently sets `user = { authenticated: true }` only. The implementation must add a `GET /api/v1/auth/me` call on login/token-load and store `user.role` in context. Role guard logic in `ChangeList` and `ChangeDetail` reads `user.role` from `AuthContext`.
