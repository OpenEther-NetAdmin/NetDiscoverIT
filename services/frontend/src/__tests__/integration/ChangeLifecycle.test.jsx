import React from 'react';
import { Flex } from '@chakra-ui/react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../../test-utils';
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

test('proposing a change updates the card status badge', async () => {
  api.getChanges
    .mockResolvedValueOnce([DRAFT_CHANGE])
    .mockResolvedValueOnce([PROPOSED_CHANGE]);
  api.proposeChange.mockResolvedValue({});
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<ChangeList />);

  expect(await screen.findByText('CHG-2026-0050')).toBeInTheDocument();
  const proposeBtn = screen.getByRole('button', { name: /propose/i });

  await userEvent.click(proposeBtn);
  const confirmBtn = await screen.findByRole('button', { name: /propose change/i });
  await userEvent.click(confirmBtn);

  await waitFor(() => expect(api.getChanges).toHaveBeenCalledTimes(2));
  expect((await screen.findAllByText('proposed')).length).toBeGreaterThan(0);
});

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

  const orgSwitcher = await screen.findByTestId('org-switcher');
  await userEvent.selectOptions(orgSwitcher, 'org-2');

  await waitFor(() => {
    expect(api.getChanges.mock.calls.length).toBeGreaterThan(callsBefore);
  });
  expect(api.setActiveOrg).toHaveBeenCalledWith('org-2');
});
