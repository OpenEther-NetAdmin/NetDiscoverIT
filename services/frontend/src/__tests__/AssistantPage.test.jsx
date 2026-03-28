import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../test-utils';
import AssistantPage from '../pages/assistant/AssistantPage';
import api from '../services/api';

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }) => <div data-testid="markdown">{children}</div>,
}));

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
    queryAssistant: jest.fn(),
  },
}));

const MOCK_RESPONSE = {
  answer: 'Two routers found in PCI scope: RTR-CORE-1, FW-EDGE-1.',
  sources: [
    { device_id: 'd1', hostname: 'RTR-CORE-1', similarity: 0.94 },
    { device_id: 'd2', hostname: 'FW-EDGE-1',  similarity: 0.87 },
  ],
  confidence: 0.92,
  query_type: 'compliance',
  retrieved_device_count: 2,
  graph_traversal_used: true,
};

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('renders empty state prompt', () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);
  expect(screen.getByText(/ask a question to get started/i)).toBeInTheDocument();
});

test('user message appears in thread after send', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Which routers are in PCI scope?');
  await userEvent.click(screen.getByLabelText(/send message/i));

  expect(screen.getByText('Which routers are in PCI scope?')).toBeInTheDocument();
});

test('textarea cleared after submit', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Hello');
  await userEvent.click(screen.getByLabelText(/send message/i));

  expect(input).toHaveValue('');
});

test('send button disabled while loading', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockReturnValue(new Promise(() => {}));
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Test question');
  const sendBtn = screen.getByLabelText(/send message/i);
  await userEvent.click(sendBtn);

  expect(sendBtn).toBeDisabled();
});

test('assistant response rendered with source chips and confidence bar', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Which routers?');
  await userEvent.click(screen.getByLabelText(/send message/i));

  expect(await screen.findByText(/Two routers found/i)).toBeInTheDocument();
  expect(screen.getByText(/RTR-CORE-1/)).toBeInTheDocument();
  expect(screen.getByText(/FW-EDGE-1/)).toBeInTheDocument();
  expect(screen.getByText('92%')).toBeInTheDocument();
});

test('error response renders red error message', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockRejectedValue(new Error('NLI pipeline error: timeout'));
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Test');
  await userEvent.click(screen.getByLabelText(/send message/i));

  expect(await screen.findByText(/Could not answer/i)).toBeInTheDocument();
});

test('Enter key submits the message', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Router count{enter}');

  await waitFor(() => expect(api.queryAssistant).toHaveBeenCalledOnce());
});

test('Clear conversation button empties message list', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Hello');
  await userEvent.click(screen.getByLabelText(/send message/i));
  await screen.findByText('Hello');

  const clearBtn = screen.getByRole('button', { name: /clear conversation/i });
  await userEvent.click(clearBtn);

  expect(screen.queryByText('Hello')).not.toBeInTheDocument();
  expect(screen.getByText(/ask a question to get started/i)).toBeInTheDocument();
});
