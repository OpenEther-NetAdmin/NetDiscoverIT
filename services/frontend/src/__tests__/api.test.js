import { api } from '../services/api';

afterEach(() => {
  api.activeOrgId = null;
  localStorage.clear();
});

describe('setActiveOrg', () => {
  test('stores activeOrgId', () => {
    api.setActiveOrg('org-123');
    expect(api.activeOrgId).toBe('org-123');
  });
});

describe('X-Org-Id header injection', () => {
  test('includes X-Org-Id header when activeOrgId is set', async () => {
    api.setActiveOrg('org-456');
    localStorage.setItem('access_token', 'test-token');

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });

    await api.request('/api/v1/test');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/test'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Org-Id': 'org-456',
        }),
      })
    );
  });

  test('does not include X-Org-Id header when activeOrgId is null', async () => {
    localStorage.setItem('access_token', 'test-token');

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });

    await api.request('/api/v1/test');

    const call = fetch.mock.calls[0];
    expect(call[1].headers['X-Org-Id']).toBeUndefined();
  });
});

describe('Change Management methods', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token');
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'change-1' }),
    });
  });

  test('getChanges calls GET /api/v1/changes with filters', async () => {
    await api.getChanges({ status: 'pending', risk_level: 'high' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes?status=pending&risk_level=high'),
      expect.any(Object)
    );
  });

  test('getChange calls GET /api/v1/changes/:id', async () => {
    await api.getChange('change-1');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1'),
      expect.any(Object)
    );
  });

  test('createChange calls POST /api/v1/changes', async () => {
    await api.createChange({ title: 'New Change' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('updateChange calls PATCH /api/v1/changes/:id', async () => {
    await api.updateChange('change-1', { title: 'Updated' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1'),
      expect.objectContaining({ method: 'PATCH' })
    );
  });

  test('deleteChange calls DELETE /api/v1/changes/:id', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 204 });
    await api.deleteChange('change-1');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1'),
      expect.objectContaining({ method: 'DELETE' })
    );
  });

  test('proposeChange calls POST /api/v1/changes/:id/propose', async () => {
    await api.proposeChange('change-1');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1/propose'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('approveChange calls POST /api/v1/changes/:id/approve with notes', async () => {
    await api.approveChange('change-1', { notes: 'Approved!' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1/approve'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('implementChange calls POST /api/v1/changes/:id/implement', async () => {
    await api.implementChange('change-1', { implementation_evidence: 'Done' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1/implement'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('verifyChange calls POST /api/v1/changes/:id/verify', async () => {
    await api.verifyChange('change-1', { verification_results: 'Passed' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1/verify'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('rollbackChange calls POST /api/v1/changes/:id/rollback', async () => {
    await api.rollbackChange('change-1', { rollback_evidence: 'Rolled back' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/changes/change-1/rollback'),
      expect.objectContaining({ method: 'POST' })
    );
  });
});

describe('MSP methods', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token');
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ organizations: [] }),
    });
  });

  test('getMspOverview calls GET /api/v1/msp/overview', async () => {
    await api.getMspOverview();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/msp/overview'),
      expect.any(Object)
    );
  });
});
