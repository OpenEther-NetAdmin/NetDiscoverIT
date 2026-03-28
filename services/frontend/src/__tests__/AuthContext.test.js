import { renderHook, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../context/AuthContext';

function makeToken(payload) {
  const encoded = Buffer.from(JSON.stringify(payload)).toString('base64');
  return `header.${encoded}.sig`;
}

afterEach(() => {
  localStorage.clear();
});

test('decodes role from JWT and sets user.role', async () => {
  localStorage.setItem('access_token', makeToken({ sub: 'u1', role: 'admin' }));
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => {
    expect(result.current.user?.role).toBe('admin');
  });
});

test('defaults role to viewer when token has no role claim', async () => {
  localStorage.setItem('access_token', makeToken({ sub: 'u1' }));
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => {
    expect(result.current.user?.role).toBe('viewer');
  });
});

test('user is null when no token in localStorage', async () => {
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => {
    expect(result.current.user).toBeNull();
  });
});
