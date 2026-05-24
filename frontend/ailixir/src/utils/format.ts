export const formatSize = (bytes?: number | null) => {
  if (!bytes) return '0 MB';
  const mb = bytes / 1024 / 1024;
  return `${mb.toFixed(2)} MB`;
};

export const formatDate = (value?: string | null) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('de-DE');
};
