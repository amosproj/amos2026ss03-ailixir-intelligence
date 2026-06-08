export const resolveDocumentContentType = (fileName: string, mimeType?: string) => {
  const allowedContentTypes = new Set(['image/png', 'image/jpeg', 'application/pdf']);
  if (mimeType && allowedContentTypes.has(mimeType)) return mimeType;

  const extension = fileName.split('.').pop()?.toLowerCase();
  if (extension === 'pdf') return 'application/pdf';
  if (extension === 'png') return 'image/png';
  if (extension === 'jpg' || extension === 'jpeg') return 'image/jpeg';

  return undefined;
};
