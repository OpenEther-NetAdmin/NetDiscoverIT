const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

class ApiService {
  constructor() {
    this.baseUrl = API_BASE_URL;
    this.activeOrgId = null;
  }

  setActiveOrg(orgId) {
    this.activeOrgId = orgId;
  }

  getToken() {
    return localStorage.getItem('access_token');
  }

  getRefreshToken() {
    return localStorage.getItem('refresh_token');
  }

  setTokens(accessToken, refreshToken) {
    localStorage.setItem('access_token', accessToken);
    if (refreshToken) {
      localStorage.setItem('refresh_token', refreshToken);
    }
  }

  clearTokens() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const token = this.getToken();

    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (this.activeOrgId) {
      headers['X-Org-Id'] = this.activeOrgId;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (response.status === 401 && token) {
        const refreshed = await this.refreshToken();
        if (refreshed) {
          return this.request(endpoint, options);
        } else {
          this.clearTokens();
          window.location.href = '/login';
          throw new Error('Session expired');
        }
      }

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
      }

      if (response.status === 204) {
        return null;
      }

      return response.json();
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  }

  async refreshToken() {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;

    try {
      const response = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (response.ok) {
        const data = await response.json();
        this.setTokens(data.access_token, data.refresh_token);
        return true;
      }
    } catch (error) {
      console.error('Token refresh failed:', error);
    }

    return false;
  }

  async login(email, password) {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();
    this.setTokens(data.access_token, data.refresh_token);
    return data;
  }

  async register(email, password, fullName) {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name: fullName }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(error.detail || 'Registration failed');
    }

    const data = await response.json();
    this.setTokens(data.access_token, data.refresh_token);
    return data;
  }

  logout() {
    this.clearTokens();
  }

  getDevices() {
    return this.request('/api/v1/devices');
  }

  getDevice(deviceId) {
    return this.request(`/api/v1/devices/${deviceId}`);
  }

  getDiscoveries() {
    return this.request('/api/v1/discoveries');
  }

  getDiscovery(discoveryId) {
    return this.request(`/api/v1/discoveries/${discoveryId}`);
  }

  createDiscovery(data) {
    return this.request('/api/v1/discoveries', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  tracePath(sourceIp, destinationIp, protocol = 'tcp', port = null) {
    return this.request('/api/v1/path/trace', {
      method: 'POST',
      body: JSON.stringify({
        source_ip: sourceIp,
        destination_ip: destinationIp,
        protocol,
        port,
      }),
    });
  }

  getStats() {
    return this.request('/api/v1/stats');
  }

  getPortalOverview() {
    return this.request('/api/v1/portal/overview');
  }

  getChanges(filters = {}) {
    const params = new URLSearchParams();
    if (filters.status) params.set('status', filters.status);
    if (filters.risk_level) params.set('risk_level', filters.risk_level);
    const query = params.toString();
    return this.request(`/api/v1/changes${query ? `?${query}` : ''}`);
  }

  getChange(id) {
    return this.request(`/api/v1/changes/${id}`);
  }

  createChange(data) {
    return this.request('/api/v1/changes', { method: 'POST', body: JSON.stringify(data) });
  }

  updateChange(id, data) {
    return this.request(`/api/v1/changes/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  deleteChange(id) {
    return this.request(`/api/v1/changes/${id}`, { method: 'DELETE' });
  }

  proposeChange(id) {
    return this.request(`/api/v1/changes/${id}/propose`, { method: 'POST' });
  }

  approveChange(id, { notes = '' } = {}) {
    return this.request(`/api/v1/changes/${id}/approve`, { method: 'POST', body: JSON.stringify({ notes }) });
  }

  implementChange(id, { implementation_evidence = '' } = {}) {
    return this.request(`/api/v1/changes/${id}/implement`, { method: 'POST', body: JSON.stringify({ implementation_evidence }) });
  }

  verifyChange(id, { verification_results = '' } = {}) {
    return this.request(`/api/v1/changes/${id}/verify`, { method: 'POST', body: JSON.stringify({ verification_results }) });
  }

  rollbackChange(id, { rollback_evidence = '' } = {}) {
    return this.request(`/api/v1/changes/${id}/rollback`, { method: 'POST', body: JSON.stringify({ rollback_evidence }) });
  }

  getMspOverview() {
    return this.request('/api/v1/msp/overview');
  }

  getTopology() {
    return this.request('/api/v1/topology');
  }

  listComplianceReports({ status, framework, skip = 0, limit = 20 } = {}) {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (framework) params.set('framework', framework);
    params.set('skip', skip);
    params.set('limit', limit);
    return this.request(`/api/v1/compliance/reports?${params.toString()}`);
  }

  createComplianceReport({ framework, format, period_start, period_end, scope_override = null }) {
    return this.request('/api/v1/compliance/reports', {
      method: 'POST',
      body: JSON.stringify({ framework, format, period_start, period_end, scope_override }),
    });
  }

  getComplianceReport(id) {
    return this.request(`/api/v1/compliance/reports/${id}`);
  }

  queryAssistant({ question, top_k = 5 }) {
    return this.request('/api/v1/query', {
      method: 'POST',
      body: JSON.stringify({ question, top_k }),
    });
  }
}

export const api = new ApiService();
export default api;
