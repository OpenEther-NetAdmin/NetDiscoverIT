import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChangeList from '../pages/changes/ChangeList';
import { renderWithProviders, setAuthRole } from '../test-utils';
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
  // Status filter is server-side: component re-fetches with status param on change.
  api.getChanges
    .mockResolvedValueOnce(CHANGES)                                  // initial load (all)
    .mockResolvedValueOnce(CHANGES.filter((c) => c.status === 'draft')); // after filter
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeList />);
  await screen.findByText('CHG-2026-0042');
  const statusSelect = screen.getByLabelText('Filter by status');
  await userEvent.selectOptions(statusSelect, 'draft');
  expect(await screen.findByText('CHG-2026-0041')).toBeInTheDocument();
  expect(screen.queryByText('CHG-2026-0042')).not.toBeInTheDocument();
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
