// Shared constants and helpers for the change management UI.

export const LIFECYCLE_STEPS = ['draft', 'proposed', 'approved', 'implemented', 'verified'];

export const STATUS_COLORS = {
  draft: 'gray',
  proposed: 'yellow',
  approved: 'green',
  implemented: 'purple',
  verified: 'teal',
  rolled_back: 'red',
};

export const RISK_COLORS = {
  low: 'green',
  medium: 'orange',
  high: 'red',
  critical: 'red',
};

// Returns the next lifecycle action the given role can perform for a change in `status`,
// or null if the user has no permitted action.
export function getActionForStatus(status, role) {
  const isAdmin = ['admin', 'msp_admin'].includes(role);
  const isEngineer = ['engineer', 'admin', 'msp_admin'].includes(role);
  if (status === 'draft' && isEngineer) return 'propose';
  if (status === 'proposed' && isAdmin) return 'approve';
  if (status === 'approved' && isEngineer) return 'implement';
  if (status === 'implemented' && isAdmin) return 'verify';
  return null;
}

// Returns true if the role can rollback a change.
export function canRollback(role, status) {
  return ['admin', 'msp_admin'].includes(role) && !['verified', 'rolled_back'].includes(status);
}
