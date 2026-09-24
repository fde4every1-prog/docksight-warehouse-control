type ApiErrorDetail = {
  code?: unknown;
  path?: unknown;
  field?: unknown;
  message?: unknown;
  errors?: unknown;
  detail?: unknown;
};

function formatPath(path: unknown): string {
  if (Array.isArray(path)) return path.map(String).join('.');
  return typeof path === 'string' ? path : '';
}

export function formatApiError(value: unknown, fallback = 'An error occurred'): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    const messages = value.map(item => formatApiError(item, '')).filter(Boolean);
    return messages.join(' · ') || fallback;
  }
  if (!value || typeof value !== 'object') return fallback;

  const detail = value as ApiErrorDetail;
  if (detail.detail !== undefined) return formatApiError(detail.detail, fallback);

  const code = typeof detail.code === 'string' ? detail.code : '';
  const path = formatPath(detail.path ?? detail.field);
  const message = typeof detail.message === 'string' ? detail.message : '';
  const heading = [code, path].filter(Boolean).join(' · ');
  const ownMessage = heading && message ? `${heading}: ${message}` : heading || message;
  const nested = Array.isArray(detail.errors)
    ? detail.errors.map(item => formatApiError(item, '')).filter(Boolean).join(' · ')
    : '';

  return [ownMessage, nested].filter(Boolean).join(' · ') || fallback;
}