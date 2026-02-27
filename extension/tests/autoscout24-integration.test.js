/**
 * Integration test for AutoScout24 extraction.
 *
 * Verifies end-to-end JSON-LD parsing with a realistic page fixture
 * rendered by JSDOM.
 *
 * Run: npm run test:extension
 */

import { describe, it, expect } from 'vitest';
import { JSDOM } from 'jsdom';
import { parseJsonLd, normalizeToAdData, buildBonusSignals } from '../extractors/autoscout24.js';


describe('AutoScout24 integration', () => {
  it('extracts vehicle data from JSON-LD in a realistic page', () => {
    const html = `
      <html><head>
        <script type="application/ld+json">${JSON.stringify({
          "@type": "Car",
          "name": "BMW 320d xDrive Touring",
          "brand": { "name": "BMW" },
          "model": "320",
          "vehicleModelDate": 2022,
          "color": "black",
          "numberOfDoors": 5,
          "vehicleSeatingCapacity": 5,
          "mileageFromOdometer": { "value": 45000, "unitCode": "KMT" },
          "vehicleEngine": {
            "enginePower": { "value": 190 },
            "fuelType": "Diesel",
          },
          "vehicleTransmission": "Automatique",
          "offers": {
            "price": 38500,
            "priceCurrency": "CHF",
            "seller": {
              "@type": "AutoDealer",
              "name": "Swiss Auto AG",
              "telephone": "+41441234567",
              "address": { "addressLocality": "Zurich", "postalCode": "8001" },
              "aggregateRating": { "ratingValue": 4.5, "reviewCount": 89 },
            }
          }
        })}</script>
      </head><body></body></html>
    `;
    const dom = new JSDOM(html);
    const jsonLd = parseJsonLd(dom.window.document);

    expect(jsonLd).not.toBeNull();
    expect(jsonLd['@type']).toBe('Car');
    expect(jsonLd.model).toBe('320');

    const adData = normalizeToAdData(null, jsonLd);
    expect(adData.make).toBe('BMW');
    expect(adData.model).toBe('320');
    expect(adData.price_eur).toBe(38500);
    expect(adData.currency).toBe('CHF');
    expect(adData.mileage_km).toBe(45000);
    expect(adData.fuel).toBe('Diesel');
    expect(adData.gearbox).toBe('Automatique');
    expect(adData.power_din_hp).toBe(190);
    expect(adData.owner_type).toBe('pro');
    expect(adData.location.city).toBe('Zurich');
    expect(adData.location.zipcode).toBe('8001');
    expect(adData.phone).toBe('+41441234567');
    expect(adData.has_phone).toBe(true);
  });

  it('builds bonus signals from JSON-LD seller rating', () => {
    const html = `
      <html><head>
        <script type="application/ld+json">${JSON.stringify({
          "@type": "Car",
          "name": "Audi A3",
          "brand": { "name": "Audi" },
          "model": "A3",
          "offers": {
            "price": 25000,
            "priceCurrency": "CHF",
            "seller": {
              "@type": "AutoDealer",
              "name": "Garage Muller",
              "aggregateRating": { "ratingValue": 4.2, "reviewCount": 33 },
            }
          }
        })}</script>
      </head><body></body></html>
    `;
    const dom = new JSDOM(html);
    const jsonLd = parseJsonLd(dom.window.document);

    // buildBonusSignals with null RSC returns empty (bonus signals are RSC-only)
    const signals = buildBonusSignals(null, jsonLd);
    expect(signals).toEqual([]);

    // With RSC containing relevant fields, signals are produced
    const rsc = {
      hadAccident: false,
      inspected: true,
      price: 25000,
      listPrice: 50000,
    };
    const signalsWithRsc = buildBonusSignals(rsc, jsonLd);
    expect(signalsWithRsc.length).toBeGreaterThanOrEqual(3);

    const accident = signalsWithRsc.find((s) => s.label === 'Accident');
    expect(accident.status).toBe('pass');

    const rating = signalsWithRsc.find((s) => s.label === 'Note Google');
    expect(rating).toBeDefined();
    expect(rating.value).toContain('4.2');

    const decote = signalsWithRsc.find((s) => s.label === 'Decote');
    expect(decote).toBeDefined();
    expect(decote.value).toBe('50%');
  });

  it('handles page with no JSON-LD', () => {
    const html = '<html><head></head><body><h1>Not a car page</h1></body></html>';
    const dom = new JSDOM(html);
    const jsonLd = parseJsonLd(dom.window.document);
    expect(jsonLd).toBeNull();
  });

  it('handles JSON-LD wrapped in @graph', () => {
    const html = `
      <html><head>
        <script type="application/ld+json">${JSON.stringify({
          "@graph": [
            { "@type": "WebPage", "name": "Some page" },
            {
              "@type": "Car",
              "name": "VW Golf",
              "brand": { "name": "Volkswagen" },
              "model": "Golf",
              "vehicleModelDate": 2021,
              "offers": { "price": 22000, "priceCurrency": "CHF" },
            },
          ]
        })}</script>
      </head><body></body></html>
    `;
    const dom = new JSDOM(html);
    const jsonLd = parseJsonLd(dom.window.document);
    expect(jsonLd).not.toBeNull();
    expect(jsonLd['@type']).toBe('Car');
    expect(jsonLd.model).toBe('Golf');

    const adData = normalizeToAdData(null, jsonLd);
    expect(adData.make).toBe('Volkswagen');
    expect(adData.model).toBe('Golf');
    expect(adData.price_eur).toBe(22000);
    expect(adData.currency).toBe('CHF');
  });
});
