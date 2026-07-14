export const typography = {
  h1: {
    fontFamily: '$heading',
    fontSize: 28,
    fontWeight: '700',
    fontStyle: 'normal',
    lineHeight: 28,
    letterSpacing: 0,
  },
  h2: {
    fontFamily: '$heading',
    fontSize: 24,
    fontWeight: '600',
    fontStyle: 'normal',
    lineHeight: 24,
    letterSpacing: 0,
  },
  markdownH1: {
    fontFamily: '$heading',
    fontSize: 26,
    fontWeight: '700',
    fontStyle: 'normal',
    lineHeight: 28,
    letterSpacing: 0,
  },
  markdownH2: {
    fontFamily: '$heading',
    fontSize: 22,
    fontWeight: '600',
    fontStyle: 'normal',
    lineHeight: 24,
    letterSpacing: 0,
  },
  markdownH3: {
    fontFamily: '$heading',
    fontSize: 18,
    fontWeight: '600',
    fontStyle: 'normal',
    lineHeight: 22,
    letterSpacing: 0,
  },
  body: {
    fontFamily: '$body',
    fontSize: 16,
    fontWeight: '400',
    lineHeight: 20,
  },
  lead: {
    fontFamily: '$body',
    fontSize: 18,
    fontWeight: '500',
    lineHeight: 22,
  },
  caption: {
    fontFamily: '$body',
    fontSize: 14,
    fontWeight: '400',
    color: '#454545',
    lineHeight: 16,
  },
} as const;

export type Typography = typeof typography;
