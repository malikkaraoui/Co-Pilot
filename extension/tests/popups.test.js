import { describe, expect, it } from 'vitest';

import { buildResultsPopup } from '../ui/popups.js';

describe('buildResultsPopup', () => {
  it('affiche une vraie demi-étoile pour la fiabilité moteur', () => {
    const html = buildResultsPopup({
      score: 72,
      is_partial: false,
      filters: [],
      vehicle: {
        make: 'Renault',
        model: 'Clio',
        year: 2024,
      },
      engine_reliability: {
        matched: true,
        score: 3.5,
        stars: '★★★½☆',
        engine_code: '0.9 TCe Renault',
        note: 'Fiabilité acceptable sur le long terme.',
      },
    });

    expect(html).toContain('data-star-fill="half"');
    expect(html).toContain('aria-label="Note fiabilité 3,5 sur 5"');
    expect(html).toContain('<svg');
    expect(html).toContain('clipPath');
    expect(html).not.toContain('★★★½☆');
    expect(html).not.toContain('½');
  });
});