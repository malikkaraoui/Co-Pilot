import { describe, it, expect } from 'vitest';
import { buildTiresPanel } from '../ui/tires.js';

describe('buildTiresPanel', () => {
  it('returns empty when tireSizes is null', () => {
    expect(buildTiresPanel(null)).toBe('');
  });

  it('returns empty when dimensions is missing/empty', () => {
    expect(buildTiresPanel({})).toBe('');
    expect(buildTiresPanel({ dimensions: [] })).toBe('');
  });

  it('renders a single dimension as compact tile', () => {
    const html = buildTiresPanel({
      dimensions: [{ size: '205/55R16', load_index: 91, speed_index: 'V' }],
      source: 'allopneus',
      source_url: 'https://example.com',
      generation: 'Golf VII',
      year_range: '2012-2021',
    });

    expect(html).toContain('Dimensions pneus');
    expect(html).toContain('okazcar-filter-item');
    expect(html).toContain('okazcar-filter-header');
    expect(html).toContain('Dimension indicative');
    expect(html).toContain('205/55 R16 91V');
    expect(html).toContain('Golf VII');
    expect(html).toContain('2012-2021');
  });

  it('renders multiple dimensions with count summary and warning', () => {
    const html = buildTiresPanel({
      dimensions: [
        { size: '195/65R15', load_index: 91, speed_index: 'H' },
        { size: '205/55R16', load_index: 91, speed_index: 'V' },
      ],
      source: 'wheel-size',
    });

    expect(html).toContain('2 dimensions possibles');
    expect(html).toContain('Plusieurs dimensions correspondent');
    expect(html).toContain('195/65 R15 91H');
    expect(html).toContain('205/55 R16 91V');
    expect(html).toContain('okazcar-filter-chevron');
  });

  it('includes a source link when source_url is provided', () => {
    const html = buildTiresPanel({
      dimensions: [{ size: '205/55R16' }],
      source: 'allopneus',
      source_url: 'https://allopneus.example/vehicule',
    });

    expect(html).toContain('Source :');
    expect(html).toContain('href="https://allopneus.example/vehicule"');
  });
});
