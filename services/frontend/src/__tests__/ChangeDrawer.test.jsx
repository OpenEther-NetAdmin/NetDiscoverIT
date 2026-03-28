import React from 'react';
import { screen } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import ChangeDrawer from '../pages/changes/ChangeDrawer';
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

test('expand button navigates to /changes/:id', async () => {
  api.getChange.mockResolvedValue(MOCK_CHANGE);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(
    <>
      <ChangeDrawer changeId="chg-uuid-1" isOpen={true} onClose={jest.fn()} />
      <Routes>
        <Route path="/changes/:id" element={<div>navigated to full page</div>} />
      </Routes>
    </>,
    { initialPath: '/changes' }
  );
  await screen.findByText('CHG-2026-0042');
  await userEvent.click(screen.getByLabelText('expand to full page'));
  expect(await screen.findByText('navigated to full page')).toBeInTheDocument();
});
