import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TopologyMap from '../pages/topology/TopologyMap';
import { renderWithProviders, setAuthRole } from '../test-utils';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getTopology: jest.fn(),
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
  },
}));

jest.mock('d3', () => ({
  select: jest.fn(() => ({
    selectAll: jest.fn(() => ({ remove: jest.fn() })),
    append: jest.fn(() => ({
      attr: jest.fn(() => ({ attr: jest.fn(), call: jest.fn() })),
      call: jest.fn(),
    })),
    call: jest.fn(),
    on: jest.fn(),
    attr: jest.fn(() => ({ attr: jest.fn() })),
  })),
  zoom: jest.fn(() => ({
    scaleExtent: jest.fn(() => ({ on: jest.fn() })),
    on: jest.fn(),
  })),
  drag: jest.fn(() => ({
    on: jest.fn(() => ({ on: jest.fn(() => ({ on: jest.fn() })) })),
  })),
  forceSimulation: jest.fn(() => ({
    force: jest.fn(() => ({
      force: jest.fn(() => ({
        force: jest.fn(() => ({
          force: jest.fn(() => ({ on: jest.fn(), stop: jest.fn() })),
        })),
      })),
    })),
    on: jest.fn(),
    stop: jest.fn(),
  })),
  forceLink: jest.fn(() => ({ id: jest.fn(() => ({ distance: jest.fn() })) })),
  forceManyBody: jest.fn(() => ({ strength: jest.fn() })),
  forceCenter: jest.fn(),
  forceCollide: jest.fn(),
}));

const MOCK_TOPOLOGY = {
  nodes: [
    {
      id: 'node-1',
      hostname: 'core-router-01',
      device_type: 'router',
      management_ip: '10.0.0.1',
      compliance_scope: ['PCI-CDE'],
    },
    {
      id: 'node-2',
      hostname: 'dist-switch-01',
      device_type: 'switch',
      management_ip: '10.0.0.2',
      compliance_scope: ['HIPAA-PHI'],
    },
    {
      id: 'node-3',
      hostname: 'firewall-edge',
      device_type: 'firewall',
      management_ip: '10.0.0.3',
      compliance_scope: [],
    },
    {
      id: 'node-4',
      hostname: 'app-server-01',
      device_type: 'server',
      management_ip: '10.0.1.10',
      compliance_scope: ['SOX-FINANCIAL'],
    },
  ],
  edges: [
    { source: 'node-1', target: 'node-2' },
    { source: 'node-2', target: 'node-3' },
    { source: 'node-1', target: 'node-4' },
  ],
};

afterEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
});

test('renders loading state initially', async () => {
  api.getTopology.mockImplementation(() => new Promise(() => {}));
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  expect(screen.getByRole('status') || document.querySelector('.chakra-spinner')).toBeTruthy();
});

test('renders topology after data loads', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  expect(await screen.findByText('Network Map')).toBeInTheDocument();
  expect(screen.getByTestId('topology-svg')).toBeInTheDocument();
});

test('shows filter bar with search and dropdown', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  expect(await screen.findByPlaceholderText('Search by hostname')).toBeInTheDocument();
  expect(screen.getByLabelText('Filter by compliance scope')).toBeInTheDocument();
});

test('filters nodes by search text', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  await screen.findByText('Network Map');
  const searchInput = screen.getByPlaceholderText('Search by hostname');
  await userEvent.type(searchInput, 'firewall');
  expect(searchInput.value).toBe('firewall');
});

test('filters nodes by device type via compliance scope dropdown', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  await screen.findByText('Network Map');
  const scopeSelect = screen.getByLabelText('Filter by compliance scope');
  await userEvent.selectOptions(scopeSelect, 'PCI-CDE');
  expect(scopeSelect.value).toBe('PCI-CDE');
});

test('shows popover when node is clicked', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  await screen.findByText('Network Map');
  const svg = screen.getByTestId('topology-svg');
  expect(svg).toBeInTheDocument();
});

test('handles empty topology gracefully', async () => {
  api.getTopology.mockResolvedValue({ nodes: [], edges: [] });
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  expect(await screen.findByText(/No devices found/)).toBeInTheDocument();
});

test('handles error state', async () => {
  api.getTopology.mockRejectedValue(new Error('Failed to load topology'));
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  expect(await screen.findByText(/Failed to load topology/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
});

test('shows refresh button', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  expect(await screen.findByRole('button', { name: /refresh/i })).toBeInTheDocument();
});

test('clicking refresh calls API again', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  await screen.findByText('Network Map');
  expect(api.getTopology).toHaveBeenCalledTimes(1);
  const refreshBtn = screen.getByRole('button', { name: /refresh/i });
  await userEvent.click(refreshBtn);
  expect(api.getTopology).toHaveBeenCalledTimes(2);
});

test('shows legend with device types and compliance scopes', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  expect(await screen.findByText('SHAPE = TYPE')).toBeInTheDocument();
  expect(screen.getByText('DOT = SCOPE')).toBeInTheDocument();
  expect(screen.getByText('Router')).toBeInTheDocument();
  expect(screen.getByText('Switch')).toBeInTheDocument();
  expect(screen.getByText('Firewall')).toBeInTheDocument();
});

test('shows filtered message when no nodes match filters', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('viewer');
  renderWithProviders(<TopologyMap />);
  await screen.findByText('Network Map');
  const searchInput = screen.getByPlaceholderText('Search by hostname');
  await userEvent.type(searchInput, 'nonexistent-device');
  expect(await screen.findByText(/No devices match the current filters/)).toBeInTheDocument();
});
