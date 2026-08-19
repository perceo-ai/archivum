import { describe, expect, it } from 'vitest';
import { ACCEPTED_INGEST_TYPES, INGEST_FORMAT_SUMMARY } from './ingestFormats';

describe('IngestPanel', () => {
  it('advertises the broad backend ingest matrix in the file picker', () => {
    expect(ACCEPTED_INGEST_TYPES).toContain('.pdf');
    expect(ACCEPTED_INGEST_TYPES).toContain('.zip');
    expect(ACCEPTED_INGEST_TYPES).toContain('.mp4');
    expect(ACCEPTED_INGEST_TYPES).toContain('.rtf');
    expect(INGEST_FORMAT_SUMMARY).toBe('Docs, media, archives, code, data, email, subtitles');
  });
});
