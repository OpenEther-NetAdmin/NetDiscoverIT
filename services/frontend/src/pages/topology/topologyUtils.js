import * as d3 from 'd3';

export const NODE_STYLES = {
  router:   { shape: 'circle',  fill: 'blue.500',   r: 18 },
  switch:   { shape: 'rect',    fill: 'gray.500',   size: 32 },
  firewall: { shape: 'diamond', fill: 'red.500',    size: 24 },
  server:   { shape: 'wideRect', fill: 'green.500', w: 36, h: 20 },
  unknown:  { shape: 'circle',  fill: 'gray.400',   r: 16 },
};

export const EDGE_COLORS = {
  connected: 'gray.300',
  trunk: 'blue.400',
  access: 'green.400',
  default: 'gray.300',
};

export const COMPLIANCE_SCOPE_OPTIONS = [
  'PCI-CDE', 'PCI-BOUNDARY', 'HIPAA-PHI', 'SOX-FINANCIAL',
  'FEDRAMP-BOUNDARY', 'ISO27001', 'SOC2', 'NIST-CSF',
];

const SCOPE_BADGE_RULES = [
  { tags: ['PCI-CDE', 'PCI-BOUNDARY'],       color: 'orange.500' },
  { tags: ['HIPAA-PHI'],                      color: 'purple.500' },
  { tags: ['SOX-FINANCIAL'],                  color: 'yellow.500' },
  { tags: ['FEDRAMP-BOUNDARY'],               color: 'red.600' },
  { tags: ['ISO27001', 'SOC2', 'NIST-CSF'],  color: 'blue.500' },
];

export function getNodeStyle(deviceType) {
  return NODE_STYLES[deviceType] || NODE_STYLES.unknown;
}

export function nodeColor(type) {
  const style = NODE_STYLES[type] || NODE_STYLES.unknown;
  return style.fill;
}

export function edgeColor(label) {
  if (!label) return EDGE_COLORS.default;
  const normalized = label.toLowerCase();
  if (normalized.includes('trunk')) return EDGE_COLORS.trunk;
  if (normalized.includes('access')) return EDGE_COLORS.access;
  if (normalized.includes('connected')) return EDGE_COLORS.connected;
  return EDGE_COLORS.default;
}

export function formatNodeLabel(node) {
  if (!node) return '';
  const hostname = node.hostname || node.id?.slice(0, 8) || 'Unknown';
  return truncate(hostname, 12);
}

export function getBadgeColor(complianceScope = []) {
  if (!complianceScope || !complianceScope.length) return null;
  for (const { tags, color } of SCOPE_BADGE_RULES) {
    if (complianceScope.some((s) => tags.includes(s))) return color;
  }
  return null;
}

export function truncate(str, maxLen) {
  if (!str) return '';
  return str.length > maxLen ? `${str.slice(0, maxLen)}\u2026` : str;
}

export function initializeNodePositions(nodes, width, height) {
  if (!nodes || !nodes.length) return nodes;
  
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) / 3;
  
  return nodes.map((node, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    const jitter = (Math.random() - 0.5) * 20;
    return {
      ...node,
      x: centerX + radius * Math.cos(angle) + jitter,
      y: centerY + radius * Math.sin(angle) + jitter,
    };
  });
}

export function applyForceSimulation(nodes, edges, width, height) {
  if (!nodes || nodes.length === 0) {
    return null;
  }
  
  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const validEdges = edges
    .filter((e) => nodeById[e.source] && nodeById[e.target])
    .map((e) => ({
      source: typeof e.source === 'string' ? nodeById[e.source] : e.source,
      target: typeof e.target === 'string' ? nodeById[e.target] : e.target,
    }));
  
  const simulation = d3
    .forceSimulation(nodes)
    .force('link', d3.forceLink(validEdges).id((d) => d.id).distance(90))
    .force('charge', d3.forceManyBody().strength(-250))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide(30));
  
  return simulation;
}

export function handleNodeClick(node, callback) {
  if (callback && typeof callback === 'function') {
    callback(node);
  }
}

export function handleNodeHover(node, callback) {
  if (callback && typeof callback === 'function') {
    callback(node);
  }
}
