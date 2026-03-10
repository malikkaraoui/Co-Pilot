import { describe, it, expect } from 'vitest';
import { normalizeAnalyzeApiUrl, apiEndpointFromAnalyzeUrl, DEFAULT_ANALYZE_URL } from '../utils/api-url.js';

describe('api-url utils', () => {
  it('normalise base origin vers /api/analyze', () => {
    expect(normalizeAnalyzeApiUrl('https://co-pilot-o546.onrender.com', DEFAULT_ANALYZE_URL))
      .toBe('https://co-pilot-o546.onrender.com/api/analyze');
  });

  it('normalise /api vers /api/analyze', () => {
    expect(normalizeAnalyzeApiUrl('https://co-pilot-o546.onrender.com/api', DEFAULT_ANALYZE_URL))
      .toBe('https://co-pilot-o546.onrender.com/api/analyze');
  });

  it('laisse /api/analyze inchangé', () => {
    expect(normalizeAnalyzeApiUrl('https://co-pilot-o546.onrender.com/api/analyze', DEFAULT_ANALYZE_URL))
      .toBe('https://co-pilot-o546.onrender.com/api/analyze');
  });

  it('construit un endpoint /market-prices/next-job depuis analyze', () => {
    expect(apiEndpointFromAnalyzeUrl('https://co-pilot-o546.onrender.com', '/market-prices/next-job', DEFAULT_ANALYZE_URL))
      .toBe('https://co-pilot-o546.onrender.com/api/market-prices/next-job');
  });
});
