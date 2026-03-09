import { describe, it, expect } from 'vitest';
import { getWinterTireSignals } from '../utils/winter-tires.js';

describe('getWinterTireSignals', () => {
  it('returns empty for null location', () => {
    expect(getWinterTireSignals(null)).toEqual([]);
  });

  it('returns empty for non-mountain department', () => {
    // Paris (75) is not in the Loi Montagne list
    const signals = getWinterTireSignals(
      { zipcode: '75001' },
      new Date(2025, 10, 15), // November 15
    );
    expect(signals).toEqual([]);
  });

  it('returns warning before season (October) for mountain dept', () => {
    // Haute-Savoie (74) in October
    const signals = getWinterTireSignals(
      { zipcode: '74000' },
      new Date(2025, 9, 15), // October 15
    );
    expect(signals.length).toBeGreaterThanOrEqual(1);
    expect(signals[0].label).toContain('Loi Montagne');
    expect(signals[0].value).toContain('1er nov');
    expect(signals[0].status).toBe('warning');
  });

  it('returns warning during season (January) for mountain dept', () => {
    // Isere (38) in January
    const signals = getWinterTireSignals(
      { zipcode: '38000' },
      new Date(2026, 0, 10), // January 10
    );
    expect(signals.length).toBeGreaterThanOrEqual(1);
    expect(signals[0].label).toContain('Loi Montagne');
    expect(signals[0].value).toContain('31 mars');
    expect(signals[0].status).toBe('warning');
  });

  it('returns vigilance after season (April) for south dept', () => {
    // Var (83) in April
    const signals = getWinterTireSignals(
      { zipcode: '83000' },
      new Date(2026, 3, 10), // April 10
    );
    expect(signals.length).toBeGreaterThanOrEqual(1);
    expect(signals[0].label).toContain('fin de saison');
    expect(signals[0].value).toContain('pneus hiver');
  });

  it('returns empty in summer for mountain dept', () => {
    // Savoie (73) in July — outside ±30 days
    const signals = getWinterTireSignals(
      { zipcode: '73000' },
      new Date(2025, 6, 15), // July 15
    );
    expect(signals).toEqual([]);
  });

  it('includes tire dimensions reminder during season', () => {
    // Haute-Savoie (74) in December
    const signals = getWinterTireSignals(
      { zipcode: '74000' },
      new Date(2025, 11, 15), // December 15
    );
    const dimSignal = signals.find((s) => s.label.includes('Dimensions'));
    expect(dimSignal).toBeDefined();
    expect(dimSignal.status).toBe('info');
  });

  it('works with department field instead of zipcode', () => {
    const signals = getWinterTireSignals(
      { department: '74' },
      new Date(2025, 10, 15), // November 15
    );
    expect(signals.length).toBeGreaterThanOrEqual(1);
  });

  it('handles department as full number string', () => {
    const signals = getWinterTireSignals(
      { department: '38' },
      new Date(2026, 0, 10),
    );
    expect(signals.length).toBeGreaterThanOrEqual(1);
  });
});
