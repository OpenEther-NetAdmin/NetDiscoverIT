import React from 'react';
import { screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../test-utils';
import ComplianceViewer from '../pages/compliance/ComplianceViewer';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
    createComplianceReport: jest.fn(),
    listComplianceReports: jest.fn(),
    getComplianceReport: jest.fn(),
  },
}));

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('full compliance flow: generate → see pending → poll resolves → Download appears', async () => {
  jest.useFakeTimers();

  const pendingReport = {
    id: 'rpt-flow-1', framework: 'pci_dss', format: 'pdf',
    status: 'pending', created_at: new Date().toISOString(),
  };
  const completedReport = { ...pendingReport, status: 'completed' };

  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.listComplianceReports.mockResolvedValueOnce({ items: [], total: 0, skip: 0, limit: 20 });
  api.createComplianceReport.mockResolvedValue(pendingReport);
  api.listComplianceReports.mockResolvedValueOnce({ items: [pendingReport], total: 1, skip: 0, limit: 20 });
  api.listComplianceReports.mockResolvedValue({ items: [completedReport], total: 1, skip: 0, limit: 20 });

  setAuthRole('admin');
  renderWithProviders(<ComplianceViewer />);

  await userEvent.click(screen.getByRole('button', { name: /PCI-DSS/i }));
  await userEvent.click(screen.getByRole('button', { name: /generate report/i }));

  await waitFor(() =>
    expect(screen.getByRole('tab', { name: /history/i }))
      .toHaveAttribute('aria-selected', 'true')
  );
  expect(await screen.findByText(/pending/i)).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(3000);
    await Promise.resolve();
  });

  await waitFor(() =>
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument()
  );

  jest.useRealTimers();
});
