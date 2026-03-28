import React from 'react';
import { screen, fireEvent } from '@testing-library/react';
import ComplianceViewer from '../pages/compliance/ComplianceViewer';
import { renderWithProviders } from '../test-utils';

jest.mock('../pages/compliance/GenerateTab', () => () => (
  <div data-testid="generate-tab">GenerateTab</div>
));

jest.mock('../pages/compliance/HistoryTab', () => () => (
  <div data-testid="history-tab">HistoryTab</div>
));

afterEach(() => {
  jest.clearAllMocks();
});

test('renders with two tabs', () => {
  renderWithProviders(<ComplianceViewer />);
  expect(screen.getByRole('tab', { name: 'Generate' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'History' })).toBeInTheDocument();
});

test('shows Generate tab by default', () => {
  renderWithProviders(<ComplianceViewer />);
  expect(screen.getByTestId('generate-tab')).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Generate' })).toHaveAttribute('aria-selected', 'true');
});

test('switches to History tab on click', () => {
  renderWithProviders(<ComplianceViewer />);
  const historyTab = screen.getByRole('tab', { name: 'History' });
  fireEvent.click(historyTab);
  expect(screen.getByTestId('history-tab')).toBeInTheDocument();
  expect(historyTab).toHaveAttribute('aria-selected', 'true');
});

test('GenerateTab renders within Generate panel', () => {
  renderWithProviders(<ComplianceViewer />);
  expect(screen.getByTestId('generate-tab')).toBeInTheDocument();
});

test('HistoryTab renders within History panel', () => {
  renderWithProviders(<ComplianceViewer />);
  fireEvent.click(screen.getByRole('tab', { name: 'History' }));
  expect(screen.getByTestId('history-tab')).toBeInTheDocument();
});
