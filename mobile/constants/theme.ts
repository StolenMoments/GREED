// OKLCH-derived hex values, amber-warm palette
export const palette = {
  // amber brand color: oklch(0.82 0.16 80) ≈ #E8B840
  amber: '#E8B840',
  amberDim: '#B8860B',

  // buy/hold/sell semantic
  buy: '#3DAD6E',      // oklch(0.72 0.15 142)
  buyLight: '#1F6B42',
  hold: '#E8B840',
  holdLight: '#B07A10',
  sell: '#D94535',     // oklch(0.65 0.20 27)
  sellLight: '#A02A1E',

  // dark surfaces (amber-tinted, not pure gray)
  dark: {
    bg:        '#0F0D09',  // oklch(0.10 0.008 80)
    surface1:  '#161310',  // oklch(0.13 0.008 80)
    surface2:  '#1D1A15',  // oklch(0.16 0.008 80)
    surface3:  '#252119',  // oklch(0.20 0.010 80)
    border:    '#2A251E',  // oklch(0.22 0.010 80)
    textPri:   '#F4EDD8',  // oklch(0.95 0.020 80)
    textSec:   '#9B9082',  // oklch(0.60 0.015 80)
    textTer:   '#5E5448',  // oklch(0.40 0.010 80)
    accent:    '#E8B840',
  },

  // light surfaces (warm off-white)
  light: {
    bg:        '#F9F5EA',  // oklch(0.97 0.015 80)
    surface1:  '#EDE4CE',  // oklch(0.93 0.018 80)
    surface2:  '#E2D8BE',  // oklch(0.89 0.018 80)
    surface3:  '#D6CBAE',
    border:    '#CFBF9E',  // oklch(0.82 0.020 80)
    textPri:   '#1E1A10',  // oklch(0.15 0.015 80)
    textSec:   '#5C5040',  // oklch(0.40 0.015 80)
    textTer:   '#8C8070',  // oklch(0.60 0.012 80)
    accent:    '#9A6E10',  // oklch(0.60 0.16 80)
  },
} as const;

export const spacing = {
  xs:   4,
  sm:   8,
  md:   12,
  base: 16,
  lg:   24,
  xl:   32,
  xxl:  48,
} as const;

export const fontSize = {
  xs:   11,
  sm:   13,
  base: 15,
  lg:   17,
  xl:   20,
  xxl:  26,
} as const;

export const radius = {
  sm:   4,
  md:   8,
  lg:   12,
  full: 9999,
} as const;
