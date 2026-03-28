export function formatMessage(msg) {
  if (!msg) return '';
  if (typeof msg === 'string') return msg;
  return msg.text || msg.answer || '';
}

export function getUserDisplayName(user) {
  if (!user) return 'Unknown User';
  if (user.display_name) return user.display_name;
  if (user.name) return user.name;
  if (user.email) return user.email.split('@')[0];
  return 'User';
}

export function processSources(sources) {
  if (!sources || !Array.isArray(sources)) return [];
  return sources.map((source) => ({
    id: source.id || source.device_id || crypto.randomUUID(),
    title: formatSourceTitle(source),
    url: source.url || null,
    snippet: source.snippet || source.description || '',
    type: getSourceType(source),
    hostname: source.hostname || null,
    similarity: source.similarity || 0,
  }));
}

export function formatSourceTitle(source) {
  if (!source) return 'Unknown Source';
  if (source.title) return source.title;
  if (source.hostname) return source.hostname;
  if (source.name) return source.name;
  if (source.device_id) return `Device ${source.device_id.slice(0, 8)}`;
  return 'Source';
}

function getSourceType(source) {
  if (source.type) return source.type;
  if (source.url) return 'external';
  if (source.device_id || source.hostname) return 'device';
  return 'unknown';
}

export function isUserMessage(msg) {
  if (!msg) return false;
  return msg.role === 'user' || msg.isUser === true;
}

export function scrollToBottom(ref) {
  if (ref && ref.current) {
    ref.current.scrollIntoView({ behavior: 'smooth' });
  }
}

export const QUERY_TYPE_COLORS = {
  topology: 'blue',
  security: 'red',
  compliance: 'orange',
  changes: 'purple',
  inventory: 'gray',
};

export function confidenceColor(score) {
  if (score >= 0.8) return 'green';
  if (score >= 0.5) return 'yellow';
  return 'red';
}
