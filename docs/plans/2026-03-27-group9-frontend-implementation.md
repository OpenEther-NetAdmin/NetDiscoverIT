# Group 9 Frontend Implementation Plan
## Change Management UI + MSP Org Switcher

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the change management list/detail UI and MSP org switcher into the existing React frontend, backed by the already-implemented backend endpoints.

**Architecture:** Feature-folder structure under `pages/changes/`. A new `OrgContext` provides active org to all pages; `AuthContext` is extended to decode `user.role` from the JWT. All API calls remain in the `api.js` singleton. No new npm packages.

**Tech Stack:** React 18, Chakra UI v2, React Router v6, Jest + React Testing Library (pre-installed via CRA), `api.js` fetch-based singleton.

**Run tests in Docker:**
```bash
make test   # runs pytest (Python) — frontend tests run separately:
cd services/frontend && npm test -- --watchAll=false
```

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/context/OrgContext.js` | Active org state, MSP org list, switchOrg |
| Create | `src/pages/changes/ChangeList.jsx` | Rich card list + filter bar |
| Create | `src/pages/changes/ChangeDetail.jsx` | Lifecycle stepper + all detail sections |
| Create | `src/pages/changes/ChangeDrawer.jsx` | Slide-over drawer wrapping ChangeDetail |
| Create | `src/pages/changes/TransitionModal.jsx` | Shared confirm modal for state transitions |
| Create | `src/__tests__/test-utils.jsx` | Render helper with all providers |
| Create | `src/__tests__/OrgContext.test.js` | OrgContext unit tests |
| Create | `src/__tests__/ChangeDetail.test.jsx` | ChangeDetail unit tests |
| Create | `src/__tests__/ChangeDrawer.test.jsx` | ChangeDrawer unit tests |
| Create | `src/__tests__/ChangeList.test.jsx` | ChangeList unit tests |
| Create | `src/__tests__/Sidebar.test.jsx` | Sidebar unit tests |
| Create | `src/__tests__/integration/ChangeLifecycle.test.jsx` | Integration tests |
| Modify | `src/context/AuthContext.js` | Decode `user.role` from JWT |
| Modify | `src/services/api.js` | `setActiveOrg`, change + MSP methods |
| Modify | `src/index.js` | Wrap app in `AuthProvider` + `OrgProvider` |
| Modify | `src/App.js` | Add `/changes` and `/changes/:id` routes |
| Modify | `src/components/Sidebar.jsx` | Changes nav item + MSP org switcher block |

---

## Task 1: Extend AuthContext to decode user.role

AuthContext currently sets `user = { authenticated: true }`. We need `user.role` for role guards in ChangeList/ChangeDetail.

**Files:**
- Modify: `src/context/AuthContext.js`
- Create: `src/__tests__/test-utils.jsx`
- Create: `src/__tests__/AuthContext.test.js`

- [ ] **Step 1: Write failing test for role decoding**

Create `src/__tests__/AuthContext.test.js`:

```js
import { renderHook, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../context/AuthContext';

function makeToken(payload) {
  const encoded = Buffer.from(JSON.stringify(payload)).toString('base64');
  return `header.${encoded}.sig`;
}

afterEach(() => {
  localStorage.clear();
});

test('decodes role from JWT and sets user.role', async () => {
  localStorage.setItem('access_token', makeToken({ sub: 'u1', role: 'admin' }));
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => {
    expect(result.current.user?.role).toBe('admin');
  });
});

test('defaults role to viewer when token has no role claim', async () => {
  localStorage.setItem('access_token', makeToken({ sub: 'u1' }));
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => {
    expect(result.current.user?.role).toBe('viewer');
  });
});

test('user is null when no token in localStorage', async () => {
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => {
    expect(result.current.user).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=AuthContext
```

Expected: FAIL — `user.role` is undefined (currently sets `{ authenticated: true }` only).

- [ ] **Step 3: Add `decodeJwtPayload` helper and extend AuthContext**

Replace the entire `src/context/AuthContext.js`:

```js
import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

function decodeJwtPayload(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return {};
  }
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      const payload = decodeJwtPayload(token);
      setUser({ authenticated: true, role: payload.role || 'viewer' });
    }
    setLoading(false);
  }, []);

  const login = async (email, password) => {
    const data = await api.login(email, password);
    const payload = decodeJwtPayload(data.access_token);
    setUser({ authenticated: true, role: payload.role || 'viewer' });
    return data;
  };

  const register = async (email, password, fullName) => {
    const data = await api.register(email, password, fullName);
    const payload = decodeJwtPayload(data.access_token);
    setUser({ authenticated: true, role: payload.role || 'viewer' });
    return data;
  };

  const logout = () => {
    api.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};

export default AuthContext;
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=AuthContext
```

Expected: PASS — 3 tests green.

- [ ] **Step 5: Create test-utils.jsx**

Create `src/__tests__/test-utils.jsx`:

```jsx
import React from 'react';
import { render } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { OrgProvider } from '../context/OrgContext';

// Create a JWT-like token with the given payload for testing
export function makeToken(payload = {}) {
  const encoded = Buffer.from(JSON.stringify(payload)).toString('base64');
  return `header.${encoded}.sig`;
}

// Sets localStorage with an access_token carrying the given role
export function setAuthRole(role = 'viewer') {
  localStorage.setItem('access_token', makeToken({ sub: 'test-user', role }));
}

export function renderWithProviders(ui, { initialPath = '/', ...renderOptions } = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ChakraProvider>
        <AuthProvider>
          <OrgProvider>
            {ui}
          </OrgProvider>
        </AuthProvider>
      </ChakraProvider>
    </MemoryRouter>,
    renderOptions,
  );
}
```

Note: `OrgProvider` doesn't exist yet — this file will fail to import until Task 3. That's fine; tests using it won't run until then.

- [ ] **Step 6: Commit**

```bash
cd services/frontend
git add src/context/AuthContext.js src/__tests__/AuthContext.test.js src/__tests__/test-utils.jsx
git commit -m "feat(frontend): decode user.role from JWT in AuthContext"
```

---

## Task 2: Extend api.js with setActiveOrg, change, and MSP methods

**Files:**
- Modify: `src/services/api.js`

- [ ] **Step 1: Add `setActiveOrg` and `X-Org-Id` header injection to request()**

Open `src/services/api.js`. In the `ApiService` class, add an `activeOrgId` property and update `request()`:

After the constructor:
```js
constructor() {
  this.baseUrl = API_BASE_URL;
  this.activeOrgId = null;
}

setActiveOrg(orgId) {
  this.activeOrgId = orgId;
}
```

Inside `request()`, after the `if (token)` block, add:
```js
if (this.activeOrgId) {
  headers['X-Org-Id'] = this.activeOrgId;
}
```

- [ ] **Step 2: Add change management methods**

Append to the `ApiService` class before the closing `}`:

```js
// ── Change Management ──────────────────────────────────────────
getChanges(filters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.risk_level) params.set('risk_level', filters.risk_level);
  const query = params.toString();
  return this.request(`/api/v1/changes${query ? `?${query}` : ''}`);
}

getChange(id) {
  return this.request(`/api/v1/changes/${id}`);
}

createChange(data) {
  return this.request('/api/v1/changes', { method: 'POST', body: JSON.stringify(data) });
}

updateChange(id, data) {
  return this.request(`/api/v1/changes/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

deleteChange(id) {
  return this.request(`/api/v1/changes/${id}`, { method: 'DELETE' });
}

proposeChange(id) {
  return this.request(`/api/v1/changes/${id}/propose`, { method: 'POST' });
}

approveChange(id, { notes = '' } = {}) {
  return this.request(`/api/v1/changes/${id}/approve`, { method: 'POST', body: JSON.stringify({ notes }) });
}

implementChange(id, { implementation_evidence = '' } = {}) {
  return this.request(`/api/v1/changes/${id}/implement`, { method: 'POST', body: JSON.stringify({ implementation_evidence }) });
}

verifyChange(id, { verification_results = '' } = {}) {
  return this.request(`/api/v1/changes/${id}/verify`, { method: 'POST', body: JSON.stringify({ verification_results }) });
}

rollbackChange(id, { rollback_evidence = '' } = {}) {
  return this.request(`/api/v1/changes/${id}/rollback`, { method: 'POST', body: JSON.stringify({ rollback_evidence }) });
}

// ── MSP ────────────────────────────────────────────────────────
getMspOverview() {
  return this.request('/api/v1/msp/overview');
}
```

- [ ] **Step 3: Commit**

```bash
cd services/frontend
git add src/services/api.js
git commit -m "feat(frontend): add change management and MSP methods to api.js"
```

---

## Task 3: Create OrgContext

**Files:**
- Create: `src/context/OrgContext.js`
- Create: `src/__tests__/OrgContext.test.js`

- [ ] **Step 1: Write failing tests**

Create `src/__tests__/OrgContext.test.js`:

```js
import { renderHook, waitFor } from '@testing-library/react';
import { OrgProvider, useOrg } from '../context/OrgContext';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
  },
}));

afterEach(() => {
  jest.clearAllMocks();
});

test('isMsp is false and managedOrgs is empty when getMspOverview fails', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  const { result } = renderHook(() => useOrg(), { wrapper: OrgProvider });
  await waitFor(() => expect(result.current.isMsp).toBe(false));
  expect(result.current.managedOrgs).toEqual([]);
});

test('isMsp is true and managedOrgs populated when getMspOverview succeeds', async () => {
  api.getMspOverview.mockResolvedValue({
    orgs: [
      { id: 'org-1', name: 'Acme Corp', device_count: 10 },
      { id: 'org-2', name: 'Beta LLC', device_count: 5 },
    ],
  });
  const { result } = renderHook(() => useOrg(), { wrapper: OrgProvider });
  await waitFor(() => expect(result.current.isMsp).toBe(true));
  expect(result.current.managedOrgs).toHaveLength(2);
  expect(result.current.activeOrg.name).toBe('Acme Corp');
});

test('switchOrg updates activeOrg and calls api.setActiveOrg', async () => {
  api.getMspOverview.mockResolvedValue({
    orgs: [
      { id: 'org-1', name: 'Acme Corp', device_count: 10 },
      { id: 'org-2', name: 'Beta LLC', device_count: 5 },
    ],
  });
  const { result } = renderHook(() => useOrg(), { wrapper: OrgProvider });
  await waitFor(() => expect(result.current.isMsp).toBe(true));

  result.current.switchOrg('org-2');

  await waitFor(() => expect(result.current.activeOrg.id).toBe('org-2'));
  expect(api.setActiveOrg).toHaveBeenCalledWith('org-2');
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=OrgContext
```

Expected: FAIL — `OrgContext` module not found.

- [ ] **Step 3: Create OrgContext.js**

Create `src/context/OrgContext.js`:

```js
import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const OrgContext = createContext(null);

export const OrgProvider = ({ children }) => {
  const [activeOrg, setActiveOrg] = useState({ id: null, name: 'My Organization', is_msp: false });
  const [managedOrgs, setManagedOrgs] = useState([]);
  const [isMsp, setIsMsp] = useState(false);

  useEffect(() => {
    api.getMspOverview()
      .then((data) => {
        const orgs = data?.orgs || [];
        if (orgs.length > 0) {
          setManagedOrgs(orgs);
          setIsMsp(true);
          setActiveOrg({ id: orgs[0].id, name: orgs[0].name, is_msp: true });
          api.setActiveOrg(orgs[0].id);
        }
      })
      .catch(() => {
        // Non-MSP user or API not yet available — no-op, defaults are correct
      });
  }, []);

  const switchOrg = (orgId) => {
    const org = managedOrgs.find((o) => o.id === orgId);
    if (!org) return;
    setActiveOrg({ id: org.id, name: org.name, is_msp: true });
    api.setActiveOrg(orgId);
  };

  return (
    <OrgContext.Provider value={{ activeOrg, managedOrgs, isMsp, switchOrg }}>
      {children}
    </OrgContext.Provider>
  );
};

export const useOrg = () => {
  const context = useContext(OrgContext);
  if (!context) throw new Error('useOrg must be used within an OrgProvider');
  return context;
};

export default OrgContext;
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=OrgContext
```

Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
cd services/frontend
git add src/context/OrgContext.js src/__tests__/OrgContext.test.js
git commit -m "feat(frontend): add OrgContext for active org and MSP org switching"
```

---

## Task 4: Wire providers into index.js + add routes in App.js

**Files:**
- Modify: `src/index.js`
- Modify: `src/App.js`

- [ ] **Step 1: Add AuthProvider and OrgProvider to index.js**

Replace the render call in `src/index.js`:

```js
import React from 'react';
import ReactDOM from 'react-dom/client';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './context/AuthContext';
import { OrgProvider } from './context/OrgContext';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1 },
  },
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ChakraProvider>
        <BrowserRouter>
          <AuthProvider>
            <OrgProvider>
              <App />
            </OrgProvider>
          </AuthProvider>
        </BrowserRouter>
      </ChakraProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
```

- [ ] **Step 2: Add /changes routes to App.js**

Replace `src/App.js`:

```jsx
import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { Box, Flex } from '@chakra-ui/react';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Devices from './pages/Devices';
import Discoveries from './pages/Discoveries';
import PathVisualizer from './pages/PathVisualizer';
import Settings from './pages/Settings';
import ChangeList from './pages/changes/ChangeList';
import ChangeDetail from './pages/changes/ChangeDetail';

function App() {
  return (
    <Flex h="100vh">
      <Sidebar />
      <Box flex="1" overflow="auto" bg="gray.50">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/portal" element={<Dashboard />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/discoveries" element={<Discoveries />} />
          <Route path="/path-visualizer" element={<PathVisualizer />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/changes" element={<ChangeList />} />
          <Route path="/changes/:id" element={<ChangeDetail />} />
        </Routes>
      </Box>
    </Flex>
  );
}

export default App;
```

- [ ] **Step 3: Verify the app starts without errors**

```bash
cd services/frontend && npm start
```

Expected: App loads at http://localhost:3000. Console shows no errors (ChangeList/ChangeDetail don't exist yet — the routes will 404 in the browser until Task 6/7 create those files, but the app itself should not crash).

Stop with Ctrl-C.

- [ ] **Step 4: Commit**

```bash
cd services/frontend
git add src/index.js src/App.js
git commit -m "feat(frontend): wire AuthProvider + OrgProvider, add /changes routes"
```

---

## Task 5: Update Sidebar — Changes nav item + MSP org switcher

**Files:**
- Modify: `src/components/Sidebar.jsx`
- Create: `src/__tests__/Sidebar.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `src/__tests__/Sidebar.test.jsx`:

```jsx
import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Sidebar from '../components/Sidebar';
import { renderWithProviders, setAuthRole } from './test-utils';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
  },
}));

afterEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
});

test('renders Changes nav item', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<Sidebar />);
  expect(await screen.findByText('Changes')).toBeInTheDocument();
});

test('MSP switcher not visible for non-MSP user', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<Sidebar />);
  await waitFor(() => expect(api.getMspOverview).toHaveBeenCalled());
  expect(screen.queryByText('ORG')).not.toBeInTheDocument();
});

test('MSP switcher visible for MSP user', async () => {
  api.getMspOverview.mockResolvedValue({
    orgs: [
      { id: 'org-1', name: 'Acme Corp', device_count: 10 },
      { id: 'org-2', name: 'Beta LLC', device_count: 5 },
    ],
  });
  setAuthRole('msp_admin');
  renderWithProviders(<Sidebar />);
  expect(await screen.findByText('Acme Corp')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=Sidebar
```

Expected: FAIL — no Changes nav item or ORG block.

- [ ] **Step 3: Update Sidebar.jsx**

Replace `src/components/Sidebar.jsx`:

```jsx
import React from 'react';
import { NavLink } from 'react-router-dom';
import { Box, VStack, Text, Icon, Flex, Menu, MenuButton, MenuList, MenuItem, Button } from '@chakra-ui/react';
import { ChevronDownIcon } from '@chakra-ui/icons';
import { FiGrid, FiServer, FiSearch, FiMap, FiSettings, FiClipboard } from 'react-icons/fi';
import { useOrg } from '../context/OrgContext';

const NavItem = ({ to, icon, children }) => (
  <NavLink to={to} style={{ width: '100%' }}>
    {({ isActive }) => (
      <Flex
        align="center"
        px={4}
        py={3}
        mx={2}
        borderRadius="md"
        color={isActive ? 'blue.500' : 'gray.600'}
        bg={isActive ? 'blue.50' : 'transparent'}
        _hover={{ bg: 'blue.50', color: 'blue.500' }}
        cursor="pointer"
        transition="all 0.2s"
      >
        <Icon as={icon} mr={3} boxSize={5} />
        <Text fontWeight={isActive ? 'semibold' : 'medium'}>{children}</Text>
      </Flex>
    )}
  </NavLink>
);

const Sidebar = () => {
  const { isMsp, activeOrg, managedOrgs, switchOrg } = useOrg();

  return (
    <Box w="240px" bg="white" borderRight="1px" borderColor="gray.200" py={4}>
      <Box px={4} mb={4}>
        <Text fontSize="xl" fontWeight="bold" color="blue.600">
          NetDiscoverIT
        </Text>
        <Text fontSize="xs" color="gray.500">
          AI Network Discovery
        </Text>
      </Box>

      {isMsp && (
        <Box px={4} mb={4}>
          <Text fontSize="9px" fontWeight="bold" color="gray.400" letterSpacing="wider" mb={1}>
            ORG
          </Text>
          <Menu>
            <MenuButton
              as={Button}
              rightIcon={<ChevronDownIcon />}
              size="sm"
              variant="outline"
              colorScheme="blue"
              width="100%"
              textAlign="left"
              fontWeight="semibold"
            >
              {activeOrg.name}
            </MenuButton>
            <MenuList>
              {managedOrgs.map((org) => (
                <MenuItem
                  key={org.id}
                  onClick={() => switchOrg(org.id)}
                  fontWeight={org.id === activeOrg.id ? 'bold' : 'normal'}
                >
                  {org.name}
                </MenuItem>
              ))}
            </MenuList>
          </Menu>
        </Box>
      )}

      <VStack spacing={1} align="stretch">
        <NavItem to="/" icon={FiGrid}>Dashboard</NavItem>
        <NavItem to="/devices" icon={FiServer}>Devices</NavItem>
        <NavItem to="/discoveries" icon={FiSearch}>Discoveries</NavItem>
        <NavItem to="/changes" icon={FiClipboard}>Changes</NavItem>
        <NavItem to="/path-visualizer" icon={FiMap}>Path Visualizer</NavItem>
        <NavItem to="/settings" icon={FiSettings}>Settings</NavItem>
      </VStack>
    </Box>
  );
};

export default Sidebar;
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=Sidebar
```

Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
cd services/frontend
git add src/components/Sidebar.jsx src/__tests__/Sidebar.test.jsx
git commit -m "feat(frontend): add Changes nav item and MSP org switcher to Sidebar"
```

---

## Task 6: Create TransitionModal (shared confirmation modal)

Used by ChangeDetail and ChangeList action buttons.

**Files:**
- Create: `src/pages/changes/TransitionModal.jsx`

- [ ] **Step 1: Create TransitionModal.jsx**

Create `src/pages/changes/TransitionModal.jsx`:

```jsx
import React, { useState } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter,
  Button, Textarea, Text,
} from '@chakra-ui/react';

const ACTION_CONFIG = {
  propose:   { label: 'Propose Change',      color: 'blue',   needsText: false, placeholder: '' },
  approve:   { label: 'Approve Change',      color: 'green',  needsText: true,  placeholder: 'Approval notes (optional)' },
  implement: { label: 'Mark as Implemented', color: 'purple', needsText: true,  placeholder: 'Implementation evidence' },
  verify:    { label: 'Verify Change',       color: 'teal',   needsText: true,  placeholder: 'Verification results' },
  rollback:  { label: 'Rollback Change',     color: 'red',    needsText: true,  placeholder: 'Reason for rollback' },
};

const TransitionModal = ({ isOpen, onClose, onConfirm, action, changeNumber, isLoading }) => {
  const [text, setText] = useState('');
  const config = ACTION_CONFIG[action] || { label: action, color: 'gray', needsText: false };

  const handleConfirm = () => {
    onConfirm(text);
    setText('');
  };

  const handleClose = () => {
    setText('');
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} isCentered>
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>{config.label}</ModalHeader>
        <ModalBody>
          <Text mb={3} color="gray.600">
            {changeNumber}
          </Text>
          {config.needsText && (
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={config.placeholder}
              rows={4}
            />
          )}
        </ModalBody>
        <ModalFooter gap={2}>
          <Button variant="ghost" onClick={handleClose}>Cancel</Button>
          <Button
            colorScheme={config.color}
            onClick={handleConfirm}
            isLoading={isLoading}
          >
            {config.label}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default TransitionModal;
```

- [ ] **Step 2: Commit**

```bash
cd services/frontend
git add src/pages/changes/TransitionModal.jsx
git commit -m "feat(frontend): add TransitionModal for change lifecycle confirmations"
```

---

## Task 7: Create ChangeDetail component

**Files:**
- Create: `src/pages/changes/ChangeDetail.jsx`
- Create: `src/__tests__/ChangeDetail.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `src/__tests__/ChangeDetail.test.jsx`:

```jsx
import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChangeDetail from '../pages/changes/ChangeDetail';
import { renderWithProviders, setAuthRole } from './test-utils';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getChange: jest.fn(),
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
    proposeChange: jest.fn(),
    approveChange: jest.fn(),
    implementChange: jest.fn(),
    verifyChange: jest.fn(),
    rollbackChange: jest.fn(),
  },
}));

const PROPOSED_CHANGE = {
  id: 'chg-uuid-1',
  change_number: 'CHG-2026-0042',
  title: 'Upgrade edge routers',
  description: 'Upgrade IOS to 17.6',
  change_type: 'firmware_upgrade',
  risk_level: 'high',
  status: 'proposed',
  affected_devices: ['dev-uuid-1', 'dev-uuid-2'],
  affected_compliance_scopes: ['PCI-CDE'],
  simulation_performed: true,
  simulation_passed: true,
  simulation_results: { tests_passed: 5 },
  external_ticket_url: null,
  pre_change_hash: 'abc123',
  post_change_hash: null,
  implementation_evidence: null,
  verification_results: null,
};

afterEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
});

test('renders lifecycle stepper with current step highlighted', async () => {
  api.getChange.mockResolvedValue(PROPOSED_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('admin');
  renderWithProviders(<ChangeDetail id="chg-uuid-1" isDrawer={false} />, { initialPath: '/changes/chg-uuid-1' });
  expect(await screen.findByText('CHG-2026-0042')).toBeInTheDocument();
  expect(screen.getByText('proposed')).toBeInTheDocument();
});

test('renders all metadata sections', async () => {
  api.getChange.mockResolvedValue(PROPOSED_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeDetail id="chg-uuid-1" isDrawer={false} />);
  expect(await screen.findByText('Upgrade edge routers')).toBeInTheDocument();
  expect(screen.getByText('Upgrade IOS to 17.6')).toBeInTheDocument();
  expect(screen.getByText('PCI-CDE')).toBeInTheDocument();
  expect(screen.getByText(/simulation passed/i)).toBeInTheDocument();
});

test('shows Approve button for admin on proposed change', async () => {
  api.getChange.mockResolvedValue(PROPOSED_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('admin');
  renderWithProviders(<ChangeDetail id="chg-uuid-1" isDrawer={false} />);
  expect(await screen.findByRole('button', { name: /approve/i })).toBeInTheDocument();
});

test('does not show Approve button for engineer on proposed change', async () => {
  api.getChange.mockResolvedValue(PROPOSED_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeDetail id="chg-uuid-1" isDrawer={false} />);
  await screen.findByText('CHG-2026-0042');
  expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
});

test('shows expand button in drawer mode', async () => {
  api.getChange.mockResolvedValue(PROPOSED_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeDetail id="chg-uuid-1" isDrawer={true} />);
  expect(await screen.findByLabelText('expand to full page')).toBeInTheDocument();
});

test('does not show expand button in full-page mode', async () => {
  api.getChange.mockResolvedValue(PROPOSED_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeDetail id="chg-uuid-1" isDrawer={false} />);
  await screen.findByText('CHG-2026-0042');
  expect(screen.queryByLabelText('expand to full page')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=ChangeDetail
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create ChangeDetail.jsx**

Create `src/pages/changes/ChangeDetail.jsx`:

```jsx
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Flex, Text, Badge, IconButton, Spinner, Button,
  Heading, Tag, TagLabel, Wrap, WrapItem,
  Divider, useDisclosure, useToast,
  Code, Collapse,
} from '@chakra-ui/react';
import { FiMaximize2, FiExternalLink, FiChevronDown, FiChevronUp, FiArrowLeft } from 'react-icons/fi';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import TransitionModal from './TransitionModal';

const LIFECYCLE_STEPS = ['draft', 'proposed', 'approved', 'implemented', 'verified'];

const STATUS_COLORS = {
  draft: 'gray', proposed: 'yellow', approved: 'green',
  implemented: 'purple', verified: 'teal', rolled_back: 'red',
};

const RISK_COLORS = { low: 'green', medium: 'orange', high: 'red', critical: 'red' };

function getActionForStatus(status, role) {
  const isAdmin = ['admin', 'msp_admin'].includes(role);
  const isEngineer = ['engineer', 'admin', 'msp_admin'].includes(role);
  if (status === 'draft' && isEngineer) return 'propose';
  if (status === 'proposed' && isAdmin) return 'approve';
  if (status === 'approved' && isEngineer) return 'implement';
  if (status === 'implemented' && isAdmin) return 'verify';
  return null;
}

const LifecycleStepper = ({ status }) => {
  const currentIndex = LIFECYCLE_STEPS.indexOf(status);
  return (
    <Flex align="center" gap={2} flexWrap="wrap" mb={4}>
      {LIFECYCLE_STEPS.map((step, index) => {
        const isDone = index < currentIndex;
        const isCurrent = step === status;
        return (
          <React.Fragment key={step}>
            <Badge
              colorScheme={isDone ? 'green' : isCurrent ? STATUS_COLORS[status] || 'blue' : 'gray'}
              variant={isCurrent ? 'solid' : 'subtle'}
              textTransform="capitalize"
              px={2} py={1}
            >
              {isDone ? `✓ ${step}` : step}
            </Badge>
            {index < LIFECYCLE_STEPS.length - 1 && (
              <Text color="gray.400" fontSize="sm" lineHeight="1">→</Text>
            )}
          </React.Fragment>
        );
      })}
      {status === 'rolled_back' && (
        <Badge colorScheme="red" variant="solid" px={2} py={1}>rolled back</Badge>
      )}
    </Flex>
  );
};

const ChangeDetail = ({ id: propId, isDrawer = false }) => {
  const params = useParams();
  const id = propId || params.id;
  const navigate = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const [change, setChange] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [simExpanded, setSimExpanded] = useState(false);

  const loadChange = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getChange(id);
      setChange(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) loadChange();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const openAction = (action) => {
    setPendingAction(action);
    onModalOpen();
  };

  const handleTransition = async (text) => {
    if (!pendingAction) return;
    setActionLoading(true);
    try {
      if (pendingAction === 'propose') await api.proposeChange(id);
      else if (pendingAction === 'approve') await api.approveChange(id, { notes: text });
      else if (pendingAction === 'implement') await api.implementChange(id, { implementation_evidence: text });
      else if (pendingAction === 'verify') await api.verifyChange(id, { verification_results: text });
      else if (pendingAction === 'rollback') await api.rollbackChange(id, { rollback_evidence: text });
      toast({ title: 'Change updated', status: 'success', duration: 3000, isClosable: true });
      onModalClose();
      await loadChange();
    } catch (err) {
      toast({ title: 'Action failed', description: err.message, status: 'error', duration: 5000, isClosable: true });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Flex justify="center" align="center" h="200px">
        <Spinner />
      </Flex>
    );
  }

  if (error || !change) {
    return (
      <Box p={4}>
        <Text color="red.500">{error || 'Change not found'}</Text>
        <Button mt={2} size="sm" onClick={loadChange}>Retry</Button>
      </Box>
    );
  }

  const userRole = user?.role || 'viewer';
  const action = getActionForStatus(change.status, userRole);
  const canRollback = ['admin', 'msp_admin'].includes(userRole) && !['verified', 'rolled_back'].includes(change.status);

  return (
    <Box p={isDrawer ? 4 : 6}>
      {/* Header */}
      <Flex align="center" justify="space-between" mb={4}>
        <Flex align="center" gap={3}>
          {!isDrawer && (
            <IconButton
              icon={<FiArrowLeft />}
              aria-label="back to changes"
              variant="ghost"
              size="sm"
              onClick={() => navigate('/changes')}
            />
          )}
          <Box>
            <Flex align="center" gap={2}>
              <Text fontWeight="bold" fontSize="lg">{change.change_number}</Text>
              <Badge colorScheme={STATUS_COLORS[change.status] || 'gray'} variant="solid">
                {change.status}
              </Badge>
              <Badge colorScheme={RISK_COLORS[change.risk_level] || 'gray'} variant="outline">
                {change.risk_level}
              </Badge>
            </Flex>
            <Text fontSize="sm" color="gray.600" mt={1}>{change.change_type}</Text>
          </Box>
        </Flex>
        {isDrawer && (
          <IconButton
            icon={<FiMaximize2 />}
            aria-label="expand to full page"
            variant="ghost"
            size="sm"
            onClick={() => navigate(`/changes/${id}`)}
          />
        )}
      </Flex>

      {/* 1. Lifecycle stepper */}
      <LifecycleStepper status={change.status} />

      {/* 2. Metadata */}
      <Heading size="sm" mb={2}>Details</Heading>
      <Box bg="gray.50" borderRadius="md" p={3} mb={4}>
        <Text fontWeight="semibold" mb={1}>{change.title}</Text>
        <Text fontSize="sm" color="gray.600">{change.description}</Text>
      </Box>

      {/* 3. Affected devices */}
      {change.affected_devices?.length > 0 && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>AFFECTED DEVICES</Text>
          <Wrap>
            {change.affected_devices.map((devId) => (
              <WrapItem key={devId}>
                <Tag size="sm" colorScheme="blue">
                  <TagLabel>{String(devId).slice(0, 8)}…</TagLabel>
                </Tag>
              </WrapItem>
            ))}
          </Wrap>
        </Box>
      )}

      {/* 4. Compliance scopes */}
      {change.affected_compliance_scopes?.length > 0 && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>COMPLIANCE SCOPES</Text>
          <Wrap>
            {change.affected_compliance_scopes.map((scope) => (
              <WrapItem key={scope}>
                <Tag size="sm" colorScheme="orange"><TagLabel>{scope}</TagLabel></Tag>
              </WrapItem>
            ))}
          </Wrap>
        </Box>
      )}

      {/* 5. Simulation */}
      {change.simulation_performed && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>SIMULATION</Text>
          <Flex align="center" gap={2}>
            <Badge colorScheme={change.simulation_passed ? 'green' : 'red'}>
              {change.simulation_passed ? 'simulation passed' : 'simulation failed'}
            </Badge>
            {change.simulation_results && (
              <Button size="xs" variant="ghost" onClick={() => setSimExpanded(!simExpanded)}>
                {simExpanded ? <FiChevronUp /> : <FiChevronDown />}
              </Button>
            )}
          </Flex>
          <Collapse in={simExpanded}>
            <Code display="block" whiteSpace="pre" mt={2} p={2} fontSize="xs" borderRadius="md">
              {JSON.stringify(change.simulation_results, null, 2)}
            </Code>
          </Collapse>
        </Box>
      )}

      {/* 6. External ticket */}
      {change.external_ticket_url && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>EXTERNAL TICKET</Text>
          <Flex align="center" gap={1}>
            <Text fontSize="sm">{change.external_ticket_id}</Text>
            <IconButton
              as="a"
              href={change.external_ticket_url}
              target="_blank"
              rel="noopener noreferrer"
              icon={<FiExternalLink />}
              aria-label="open ticket"
              variant="ghost"
              size="xs"
            />
          </Flex>
        </Box>
      )}

      {/* 7. Evidence */}
      {(change.pre_change_hash || change.post_change_hash || change.implementation_evidence || change.verification_results) && (
        <Box mb={4}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" mb={1}>EVIDENCE</Text>
          <Box fontSize="xs" color="gray.600">
            {change.pre_change_hash && <Text>Pre-change hash: <Code>{change.pre_change_hash.slice(0, 12)}…</Code></Text>}
            {change.post_change_hash && <Text>Post-change hash: <Code>{change.post_change_hash.slice(0, 12)}…</Code></Text>}
            {change.implementation_evidence && <Text mt={1}>{change.implementation_evidence}</Text>}
            {change.verification_results && <Text mt={1}>{change.verification_results}</Text>}
          </Box>
        </Box>
      )}

      {/* 8. Action button */}
      <Divider mb={4} />
      <Flex gap={2}>
        {action && (
          <Button colorScheme={STATUS_COLORS[change.status] || 'blue'} flex="1" onClick={() => openAction(action)}>
            {action.charAt(0).toUpperCase() + action.slice(1)}
          </Button>
        )}
        {canRollback && (
          <Button colorScheme="red" variant="outline" onClick={() => openAction('rollback')}>
            Rollback
          </Button>
        )}
      </Flex>

      <TransitionModal
        isOpen={isModalOpen}
        onClose={onModalClose}
        onConfirm={handleTransition}
        action={pendingAction}
        changeNumber={change.change_number}
        isLoading={actionLoading}
      />
    </Box>
  );
};

export default ChangeDetail;
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=ChangeDetail
```

Expected: PASS — 6 tests green.

- [ ] **Step 5: Commit**

```bash
cd services/frontend
git add src/pages/changes/ChangeDetail.jsx src/__tests__/ChangeDetail.test.jsx
git commit -m "feat(frontend): add ChangeDetail with lifecycle stepper and role-aware actions"
```

---

## Task 8: Create ChangeDrawer component

**Files:**
- Create: `src/pages/changes/ChangeDrawer.jsx`
- Create: `src/__tests__/ChangeDrawer.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `src/__tests__/ChangeDrawer.test.jsx`:

```jsx
import React from 'react';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChangeDrawer from '../pages/changes/ChangeDrawer';
import { renderWithProviders, setAuthRole } from './test-utils';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getChange: jest.fn(),
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
    proposeChange: jest.fn(),
    approveChange: jest.fn(),
    implementChange: jest.fn(),
    verifyChange: jest.fn(),
    rollbackChange: jest.fn(),
  },
}));

const MOCK_CHANGE = {
  id: 'chg-uuid-1', change_number: 'CHG-2026-0042', title: 'Upgrade edge routers',
  description: 'desc', change_type: 'firmware_upgrade', risk_level: 'high', status: 'draft',
  affected_devices: [], affected_compliance_scopes: [], simulation_performed: false,
  external_ticket_url: null, pre_change_hash: null, post_change_hash: null,
  implementation_evidence: null, verification_results: null,
};

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('renders drawer when isOpen=true', async () => {
  api.getChange.mockResolvedValue(MOCK_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(
    <ChangeDrawer changeId="chg-uuid-1" isOpen={true} onClose={jest.fn()} />
  );
  expect(await screen.findByText('CHG-2026-0042')).toBeInTheDocument();
});

test('calls onClose when close button clicked', async () => {
  api.getChange.mockResolvedValue(MOCK_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  const onClose = jest.fn();
  setAuthRole('engineer');
  renderWithProviders(
    <ChangeDrawer changeId="chg-uuid-1" isOpen={true} onClose={onClose} />
  );
  await screen.findByText('CHG-2026-0042');
  await userEvent.click(screen.getByLabelText('Close'));
  expect(onClose).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=ChangeDrawer
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create ChangeDrawer.jsx**

Create `src/pages/changes/ChangeDrawer.jsx`:

```jsx
import React from 'react';
import {
  Drawer, DrawerOverlay, DrawerContent, DrawerCloseButton,
  DrawerHeader, DrawerBody, Flex, Text, Badge,
} from '@chakra-ui/react';
import ChangeDetail from './ChangeDetail';

const STATUS_COLORS = {
  draft: 'gray', proposed: 'yellow', approved: 'green',
  implemented: 'purple', verified: 'teal', rolled_back: 'red',
};

const ChangeDrawer = ({ changeId, isOpen, onClose, statusHint, changeNumberHint }) => {
  return (
    <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="lg">
      <DrawerOverlay />
      <DrawerContent>
        <DrawerCloseButton />
        <DrawerHeader>
          <Flex align="center" gap={2}>
            <Text>{changeNumberHint || 'Change Detail'}</Text>
            {statusHint && (
              <Badge colorScheme={STATUS_COLORS[statusHint] || 'gray'} variant="solid">
                {statusHint}
              </Badge>
            )}
          </Flex>
        </DrawerHeader>
        <DrawerBody p={0}>
          {isOpen && changeId && (
            <ChangeDetail id={changeId} isDrawer={true} />
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default ChangeDrawer;
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=ChangeDrawer
```

Expected: PASS — 2 tests green.

- [ ] **Step 5: Commit**

```bash
cd services/frontend
git add src/pages/changes/ChangeDrawer.jsx src/__tests__/ChangeDrawer.test.jsx
git commit -m "feat(frontend): add ChangeDrawer slide-over component"
```

---

## Task 9: Create ChangeList component

**Files:**
- Create: `src/pages/changes/ChangeList.jsx`
- Create: `src/__tests__/ChangeList.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `src/__tests__/ChangeList.test.jsx`:

```jsx
import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChangeList from '../pages/changes/ChangeList';
import { renderWithProviders, setAuthRole } from './test-utils';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getChanges: jest.fn(),
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
  },
}));

const CHANGES = [
  {
    id: 'chg-1', change_number: 'CHG-2026-0042', title: 'Upgrade edge routers',
    status: 'proposed', risk_level: 'high', affected_devices: ['d1', 'd2'],
    affected_compliance_scopes: ['PCI-CDE'], simulation_performed: true,
    simulation_passed: true, external_ticket_url: null,
  },
  {
    id: 'chg-2', change_number: 'CHG-2026-0041', title: 'Update ACL',
    status: 'draft', risk_level: 'medium', affected_devices: ['d1'],
    affected_compliance_scopes: [], simulation_performed: false,
    simulation_passed: false, external_ticket_url: 'https://jira.example.com/JIRA-1',
  },
];

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('renders change cards from API response', async () => {
  api.getChanges.mockResolvedValue(CHANGES);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeList />);
  expect(await screen.findByText('CHG-2026-0042')).toBeInTheDocument();
  expect(screen.getByText('CHG-2026-0041')).toBeInTheDocument();
  expect(screen.getByText('Upgrade edge routers')).toBeInTheDocument();
});

test('filter by status narrows the visible cards', async () => {
  api.getChanges.mockResolvedValue(CHANGES);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeList />);
  await screen.findByText('CHG-2026-0042');
  const statusSelect = screen.getByLabelText('Filter by status');
  await userEvent.selectOptions(statusSelect, 'draft');
  expect(screen.queryByText('CHG-2026-0042')).not.toBeInTheDocument();
  expect(screen.getByText('CHG-2026-0041')).toBeInTheDocument();
});

test('shows Propose button for engineer on draft change', async () => {
  api.getChanges.mockResolvedValue(CHANGES);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeList />);
  await screen.findByText('CHG-2026-0041');
  expect(screen.getAllByRole('button', { name: /propose/i })).toHaveLength(1);
});

test('shows Approve button for admin on proposed change', async () => {
  api.getChanges.mockResolvedValue(CHANGES);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('admin');
  renderWithProviders(<ChangeList />);
  await screen.findByText('CHG-2026-0042');
  expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
});

test('no action buttons visible for viewer', async () => {
  api.getChanges.mockResolvedValue(CHANGES);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<ChangeList />);
  await screen.findByText('CHG-2026-0042');
  expect(screen.queryByRole('button', { name: /propose|approve|implement|verify/i })).not.toBeInTheDocument();
});

test('clicking a card opens the drawer', async () => {
  api.getChanges.mockResolvedValue(CHANGES);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeList />);
  const card = await screen.findByText('Upgrade edge routers');
  await userEvent.click(card);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=ChangeList
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create ChangeList.jsx**

Create `src/pages/changes/ChangeList.jsx`:

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Heading, Text, Badge, Button, Spinner,
  Select, Input, InputGroup, InputLeftElement,
  Card, CardBody, Wrap, WrapItem, Tag, TagLabel,
  useDisclosure, useToast,
} from '@chakra-ui/react';
import { FiSearch, FiRefreshCw, FiExternalLink } from 'react-icons/fi';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useOrg } from '../../context/OrgContext';
import ChangeDrawer from './ChangeDrawer';
import TransitionModal from './TransitionModal';

const STATUS_COLORS = {
  draft: 'gray', proposed: 'yellow', approved: 'green',
  implemented: 'purple', verified: 'teal', rolled_back: 'red',
};
const RISK_COLORS = { low: 'green', medium: 'orange', high: 'red', critical: 'red' };

function getActionForStatus(status, role) {
  const isAdmin = ['admin', 'msp_admin'].includes(role);
  const isEngineer = ['engineer', 'admin', 'msp_admin'].includes(role);
  if (status === 'draft' && isEngineer) return 'propose';
  if (status === 'proposed' && isAdmin) return 'approve';
  if (status === 'approved' && isEngineer) return 'implement';
  if (status === 'implemented' && isAdmin) return 'verify';
  return null;
}

const ChangeList = () => {
  const { user } = useAuth();
  const { activeOrg } = useOrg();
  const toast = useToast();
  const { isOpen: isDrawerOpen, onOpen: onDrawerOpen, onClose: onDrawerClose } = useDisclosure();
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();

  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedChange, setSelectedChange] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  const loadChanges = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getChanges({ status: statusFilter, risk_level: riskFilter });
      setChanges(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, riskFilter]);

  useEffect(() => {
    loadChanges();
  }, [loadChanges, activeOrg]);

  const openDrawer = (change) => {
    setSelectedChange(change);
    onDrawerOpen();
  };

  const openAction = (e, change, action) => {
    e.stopPropagation();
    setSelectedChange(change);
    setPendingAction(action);
    onModalOpen();
  };

  const handleTransition = async (text) => {
    if (!pendingAction || !selectedChange) return;
    setActionLoading(true);
    try {
      const id = selectedChange.id;
      if (pendingAction === 'propose') await api.proposeChange(id);
      else if (pendingAction === 'approve') await api.approveChange(id, { notes: text });
      else if (pendingAction === 'implement') await api.implementChange(id, { implementation_evidence: text });
      else if (pendingAction === 'verify') await api.verifyChange(id, { verification_results: text });
      else if (pendingAction === 'rollback') await api.rollbackChange(id, { rollback_evidence: text });
      toast({ title: 'Change updated', status: 'success', duration: 3000, isClosable: true });
      onModalClose();
      await loadChanges();
    } catch (err) {
      toast({ title: 'Action failed', description: err.message, status: 'error', duration: 5000, isClosable: true });
    } finally {
      setActionLoading(false);
    }
  };

  const filtered = changes.filter((c) => {
    const matchesStatus = !statusFilter || c.status === statusFilter;
    const matchesRisk = !riskFilter || c.risk_level === riskFilter;
    const matchesSearch = !search ||
      c.title?.toLowerCase().includes(search.toLowerCase()) ||
      c.change_number?.toLowerCase().includes(search.toLowerCase());
    return matchesStatus && matchesRisk && matchesSearch;
  });

  const userRole = user?.role || 'viewer';

  if (loading) {
    return (
      <Box p={6}>
        <Flex justify="center" align="center" h="400px"><Spinner size="xl" /></Flex>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={6}>
        <Text color="red.500">{error}</Text>
        <Button mt={4} onClick={loadChanges}>Retry</Button>
      </Box>
    );
  }

  return (
    <Box p={6}>
      <Flex justify="space-between" align="center" mb={6}>
        <Heading size="lg">Changes</Heading>
        <Button leftIcon={<FiRefreshCw />} size="sm" onClick={loadChanges}>Refresh</Button>
      </Flex>

      {/* Filter bar */}
      <Flex gap={3} mb={6} flexWrap="wrap">
        <InputGroup maxW="280px">
          <InputLeftElement pointerEvents="none"><FiSearch color="gray.300" /></InputLeftElement>
          <Input
            placeholder="Search by title or number"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </InputGroup>
        <Select
          aria-label="Filter by status"
          maxW="180px"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          {['draft', 'proposed', 'approved', 'implemented', 'verified', 'rolled_back'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </Select>
        <Select
          aria-label="Filter by risk"
          maxW="160px"
          value={riskFilter}
          onChange={(e) => setRiskFilter(e.target.value)}
        >
          <option value="">All risks</option>
          {['low', 'medium', 'high', 'critical'].map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </Select>
      </Flex>

      {/* Change cards */}
      {filtered.length === 0 ? (
        <Box textAlign="center" py={12} color="gray.500">
          No changes found. Adjust filters or create a new change.
        </Box>
      ) : (
        <Flex direction="column" gap={3}>
          {filtered.map((change) => {
            const action = getActionForStatus(change.status, userRole);
            return (
              <Card
                key={change.id}
                cursor="pointer"
                _hover={{ borderColor: 'blue.300', shadow: 'sm' }}
                borderWidth="1px"
                onClick={() => openDrawer(change)}
              >
                <CardBody>
                  <Flex justify="space-between" align="flex-start">
                    <Box flex="1" mr={4}>
                      <Flex align="center" gap={2} mb={1} flexWrap="wrap">
                        <Badge colorScheme="blue" variant="outline" fontSize="xs" fontWeight="bold">
                          {change.change_number}
                        </Badge>
                        <Badge colorScheme={STATUS_COLORS[change.status] || 'gray'} variant="solid" fontSize="xs">
                          {change.status}
                        </Badge>
                        <Badge colorScheme={RISK_COLORS[change.risk_level] || 'gray'} variant="outline" fontSize="xs">
                          {change.risk_level}
                        </Badge>
                      </Flex>
                      <Text fontWeight="semibold" mb={2}>{change.title}</Text>
                      <Flex align="center" gap={3} flexWrap="wrap">
                        <Text fontSize="xs" color="gray.500">
                          {change.affected_devices?.length || 0} device{change.affected_devices?.length !== 1 ? 's' : ''}
                        </Text>
                        {change.affected_compliance_scopes?.length > 0 && (
                          <Wrap spacing={1}>
                            {change.affected_compliance_scopes.map((scope) => (
                              <WrapItem key={scope}>
                                <Tag size="sm" colorScheme="orange"><TagLabel>{scope}</TagLabel></Tag>
                              </WrapItem>
                            ))}
                          </Wrap>
                        )}
                        {change.simulation_performed && (
                          <Badge colorScheme={change.simulation_passed ? 'green' : 'red'} variant="subtle" fontSize="xs">
                            {change.simulation_passed ? '✓ sim' : '✗ sim'}
                          </Badge>
                        )}
                        {change.external_ticket_url && (
                          <Flex
                            as="a"
                            href={change.external_ticket_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            align="center"
                            gap={1}
                            color="blue.500"
                            fontSize="xs"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <FiExternalLink size={10} />
                            <Text>{change.external_ticket_id || 'ticket'}</Text>
                          </Flex>
                        )}
                      </Flex>
                    </Box>
                    {action && (
                      <Button
                        colorScheme={STATUS_COLORS[change.status] || 'blue'}
                        size="sm"
                        flexShrink={0}
                        onClick={(e) => openAction(e, change, action)}
                      >
                        {action.charAt(0).toUpperCase() + action.slice(1)}
                      </Button>
                    )}
                  </Flex>
                </CardBody>
              </Card>
            );
          })}
        </Flex>
      )}

      <ChangeDrawer
        changeId={selectedChange?.id}
        isOpen={isDrawerOpen}
        onClose={onDrawerClose}
        statusHint={selectedChange?.status}
        changeNumberHint={selectedChange?.change_number}
      />

      <TransitionModal
        isOpen={isModalOpen}
        onClose={onModalClose}
        onConfirm={handleTransition}
        action={pendingAction}
        changeNumber={selectedChange?.change_number}
        isLoading={actionLoading}
      />
    </Box>
  );
};

export default ChangeList;
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=ChangeList
```

Expected: PASS — 6 tests green.

- [ ] **Step 5: Commit**

```bash
cd services/frontend
git add src/pages/changes/ChangeList.jsx src/__tests__/ChangeList.test.jsx
git commit -m "feat(frontend): add ChangeList with rich cards, filters, and role-aware actions"
```

---

## Task 10: Integration tests

**Files:**
- Create: `src/__tests__/integration/ChangeLifecycle.test.jsx`

- [ ] **Step 1: Write integration tests**

Create `src/__tests__/integration/ChangeLifecycle.test.jsx`:

```jsx
import React from 'react';
import { Flex } from '@chakra-ui/react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../test-utils';
import ChangeList from '../../pages/changes/ChangeList';
import Sidebar from '../../components/Sidebar';
import api from '../../services/api';

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    getChanges: jest.fn(),
    getChange: jest.fn(),
    proposeChange: jest.fn(),
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
  },
}));

const DRAFT_CHANGE = {
  id: 'chg-1', change_number: 'CHG-2026-0050', title: 'Add firewall rule',
  status: 'draft', risk_level: 'low', affected_devices: ['dev-1'],
  affected_compliance_scopes: [], simulation_performed: false,
  simulation_passed: false, external_ticket_url: null,
};

const PROPOSED_CHANGE = { ...DRAFT_CHANGE, status: 'proposed' };

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

// Integration: list → propose → card status updates
test('proposing a change updates the card status badge', async () => {
  api.getChanges
    .mockResolvedValueOnce([DRAFT_CHANGE])
    .mockResolvedValueOnce([PROPOSED_CHANGE]);
  api.proposeChange.mockResolvedValue({});
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeList />);

  // Initial render: draft card with Propose button
  expect(await screen.findByText('CHG-2026-0050')).toBeInTheDocument();
  const proposeBtn = screen.getByRole('button', { name: /propose/i });

  // Click Propose → modal opens → confirm
  await userEvent.click(proposeBtn);
  const confirmBtn = await screen.findByRole('button', { name: /propose change/i });
  await userEvent.click(confirmBtn);

  // After transition, list reloads — status badge updates to proposed
  await waitFor(() => expect(api.getChanges).toHaveBeenCalledTimes(2));
  expect(await screen.findByText('proposed')).toBeInTheDocument();
});

// Integration: viewer sees no action buttons on any card
test('viewer role sees no action buttons', async () => {
  api.getChanges.mockResolvedValue([
    DRAFT_CHANGE,
    { ...DRAFT_CHANGE, id: 'chg-2', change_number: 'CHG-2026-0051', status: 'proposed' },
  ]);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<ChangeList />);

  await screen.findByText('CHG-2026-0050');
  expect(screen.queryByRole('button', { name: /propose|approve|implement|verify/i })).not.toBeInTheDocument();
});

// Integration: MSP org switch causes getChanges to be called again
// Render Sidebar + ChangeList together so the org switcher is in the tree
test('switching org reloads changes', async () => {
  api.getChanges.mockResolvedValue([DRAFT_CHANGE]);
  api.getMspOverview.mockResolvedValue({
    orgs: [
      { id: 'org-1', name: 'Acme Corp', device_count: 5 },
      { id: 'org-2', name: 'Beta LLC', device_count: 3 },
    ],
  });
  api.setActiveOrg.mockImplementation(() => {});
  setAuthRole('msp_admin');

  const Layout = () => (
    <Flex>
      <Sidebar />
      <ChangeList />
    </Flex>
  );
  renderWithProviders(<Layout />);

  await screen.findByText('CHG-2026-0050');
  const callsBefore = api.getChanges.mock.calls.length;

  // Open MSP org menu and switch to Beta LLC
  const orgButton = await screen.findByText('Acme Corp');
  await userEvent.click(orgButton);
  const betaOption = await screen.findByText('Beta LLC');
  await userEvent.click(betaOption);

  await waitFor(() => {
    expect(api.getChanges.mock.calls.length).toBeGreaterThan(callsBefore);
  });
  expect(api.setActiveOrg).toHaveBeenCalledWith('org-2');
});
```

- [ ] **Step 2: Run integration tests**

```bash
cd services/frontend && npm test -- --watchAll=false --testPathPattern=ChangeLifecycle
```

Expected: PASS — 3 integration tests green.

- [ ] **Step 3: Run the full test suite**

```bash
cd services/frontend && npm test -- --watchAll=false
```

Expected: All tests pass. Note the total count.

- [ ] **Step 4: Commit**

```bash
cd services/frontend
git add src/__tests__/integration/ChangeLifecycle.test.jsx
git commit -m "test(frontend): add Group 9 integration tests for change lifecycle and MSP switch"
```

---

## Verification Checklist

Before marking Group 9 complete, verify these manually in the browser:

- [ ] Navigate to `/changes` — list renders, filter bar works
- [ ] Click a card — drawer slides in from the right
- [ ] Click the expand icon in drawer — navigates to `/changes/:id` full page
- [ ] Back button on full page returns to `/changes`
- [ ] MSP user sees org switcher in sidebar; non-MSP user does not
- [ ] Switching org (MSP user) causes the change list to reload
- [ ] Action buttons only appear for the correct role
- [ ] Clicking an action button opens the TransitionModal
- [ ] Successful transition shows toast and updates card status

---

## Claw-Memory Update

After all tasks are complete, update `/tmp/claw-memory/current-state.md` to mark Group 9 done, then commit and push:

```bash
cd /tmp/claw-memory
git add -A
git commit -m "update: Group 9 frontend complete — change management UI + MSP switcher"
git push
```
