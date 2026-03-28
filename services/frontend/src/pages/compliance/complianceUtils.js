export const FRAMEWORKS = [
  { id: 'pci_dss',   label: 'PCI-DSS v4.0', colorScheme: 'red' },
  { id: 'hipaa',     label: 'HIPAA',         colorScheme: 'purple' },
  { id: 'sox_itgc',  label: 'SOX ITGC',      colorScheme: 'yellow' },
  { id: 'iso_27001', label: 'ISO 27001',      colorScheme: 'blue' },
  { id: 'nist_csf',  label: 'NIST CSF',      colorScheme: 'cyan' },
  { id: 'fedramp',   label: 'FedRAMP',        colorScheme: 'green' },
  { id: 'soc2',      label: 'SOC 2',          colorScheme: 'teal' },
];

export const STATUS_COLORS = {
  pending:    'yellow',
  generating: 'yellow',
  completed:  'green',
  failed:     'red',
};

export const SEVERITY_COLORS = {
  critical: 'red',
  high:     'orange',
  medium:   'yellow',
  low:      'blue',
  info:     'gray',
};

export const FORMAT_LABELS = {
  pdf:  'PDF',
  docx: 'DOCX',
  both: 'PDF + DOCX',
};

export function isTerminalStatus(status) {
  return status === 'completed' || status === 'failed';
}

export function daysAgo(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split('T')[0];
}

export function today() {
  return new Date().toISOString().split('T')[0];
}

export function formatReportDate(dateString) {
  if (!dateString) return '';
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

export function getReportStatus(report) {
  if (!report) return 'pending';
  const status = report.status?.toLowerCase();
  if (status === 'completed') return 'completed';
  if (status === 'failed') return 'failed';
  if (status === 'generating') return 'generating';
  return 'pending';
}

export function formatComplianceScore(score) {
  if (score === null || score === undefined) return 'N/A';
  const numScore = typeof score === 'number' ? score : parseFloat(score);
  if (isNaN(numScore)) return 'N/A';
  return `${Math.round(numScore)}%`;
}

export function parseReportContent(content) {
  if (!content) return null;
  if (typeof content === 'object') return content;
  try {
    return JSON.parse(content);
  } catch {
    return null;
  }
}

export function groupFindingsBySeverity(findings) {
  if (!findings || !Array.isArray(findings)) {
    return {
      critical: [],
      high: [],
      medium: [],
      low: [],
      info: [],
    };
  }
  return findings.reduce(
    (groups, finding) => {
      const severity = (finding.severity || 'info').toLowerCase();
      const normalized = ['critical', 'high', 'medium', 'low', 'info'].includes(severity)
        ? severity
        : 'info';
      groups[normalized].push(finding);
      return groups;
    },
    {
      critical: [],
      high: [],
      medium: [],
      low: [],
      info: [],
    }
  );
}

export function severityColor(severity) {
  if (!severity) return 'gray.500';
  const normalized = severity.toLowerCase();
  const scheme = SEVERITY_COLORS[normalized];
  if (!scheme) return 'gray.500';
  return `${scheme}.500`;
}

export function statusColor(status) {
  if (!status) return 'gray.500';
  const normalized = status.toLowerCase();
  const scheme = STATUS_COLORS[normalized];
  if (!scheme) return 'gray.500';
  return `${scheme}.500`;
}
