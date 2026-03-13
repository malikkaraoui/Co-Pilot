import { backendFetch } from '../utils/fetch.js';

describe('backendFetch', () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('retourne un blob pour une reponse PDF proxyee', async () => {
    globalThis.fetch = vi.fn();
    globalThis.chrome = {
      runtime: {
        sendMessage: vi.fn((payload, callback) => {
          callback({
            ok: true,
            status: 200,
            contentType: 'application/pdf',
            bodyBase64: 'JVBERi0=',
          });
        }),
      },
    };

    const resp = await backendFetch('http://localhost:5001/api/scan-report', {
      method: 'POST',
    });

    const blob = await resp.blob();
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe('application/pdf');
    expect(blob.size).toBe(5);
  });
});