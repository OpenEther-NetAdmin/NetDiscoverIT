import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChangeDetail from '../pages/changes/ChangeDetail';
import { renderWithProviders, setAuthRole } from '../test-utils';
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
  expect(screen.getAllByText('proposed').length).toBeGreaterThan(0);
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
