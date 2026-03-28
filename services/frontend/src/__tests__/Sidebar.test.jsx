import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import Sidebar from '../components/Sidebar';
import { renderWithProviders, setAuthRole } from '../test-utils';
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
  expect(screen.queryByTestId('org-switcher')).not.toBeInTheDocument();
});

test('MSP switcher visible for MSP user', async () => {
  const mockOrgs = [
    { id: 'org-1', name: 'Acme Corp', device_count: 10 },
    { id: 'org-2', name: 'Beta LLC', device_count: 5 },
  ];
  api.getMspOverview.mockResolvedValue({ orgs: mockOrgs });
  setAuthRole('msp_admin');
  renderWithProviders(<Sidebar />);
  const select = await screen.findByTestId('org-switcher');
  expect(select).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });
});
