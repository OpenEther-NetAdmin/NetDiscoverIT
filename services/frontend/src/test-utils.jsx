import React from 'react';
import { render } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { OrgProvider } from './context/OrgContext';
import '@testing-library/jest-dom';

export function makeToken(payload = {}) {
  const encoded = Buffer.from(JSON.stringify(payload)).toString('base64');
  return `header.${encoded}.sig`;
}

export function setAuthRole(role = 'viewer') {
  localStorage.setItem('access_token', makeToken({ sub: 'test-user', role }));
}

export function renderWithProviders(ui, { initialPath = '/', ...renderOptions } = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ChakraProvider>
        <AuthProvider>
          <OrgProvider>
            {ui}
          </OrgProvider>
        </AuthProvider>
      </ChakraProvider>
    </MemoryRouter>,
    renderOptions,
  );
}
