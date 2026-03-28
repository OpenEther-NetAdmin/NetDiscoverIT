import { renderHook, waitFor, act } from '@testing-library/react';
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

  act(() => {
    result.current.switchOrg('org-2');
  });

  await waitFor(() => expect(result.current.activeOrg.id).toBe('org-2'));
  expect(api.setActiveOrg).toHaveBeenCalledWith('org-2');
});
