import React from 'react';
import { Text, View, StyleSheet } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { palette, fontSize, spacing, radius } from '@/constants/theme';
import type { Judgment } from '@/api/types';

const judgmentConfig: Record<Judgment, { label: string; darkBg: string; darkText: string; lightBg: string; lightText: string }> = {
  매수: {
    label:     '매수',
    darkBg:    '#1A3D2B',
    darkText:  palette.buy,
    lightBg:   '#D0EDD9',
    lightText: palette.buyLight,
  },
  홀드: {
    label:     '홀드',
    darkBg:    '#3A2D0A',
    darkText:  palette.hold,
    lightBg:   '#F5E8C0',
    lightText: palette.holdLight,
  },
  매도: {
    label:     '매도',
    darkBg:    '#3D1410',
    darkText:  palette.sell,
    lightBg:   '#F5D0CC',
    lightText: palette.sellLight,
  },
};

interface Props {
  judgment: Judgment;
  size?: 'sm' | 'md';
}

export function JudgmentBadge({ judgment, size = 'md' }: Props) {
  const { isDark } = useTheme();
  const cfg = judgmentConfig[judgment];

  return (
    <View
      style={[
        styles.pill,
        size === 'sm' && styles.pillSm,
        { backgroundColor: isDark ? cfg.darkBg : cfg.lightBg },
      ]}
    >
      <Text
        style={[
          styles.label,
          size === 'sm' && styles.labelSm,
          { color: isDark ? cfg.darkText : cfg.lightText },
        ]}
      >
        {cfg.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical:   spacing.xs,
    borderRadius:      radius.full,
    alignSelf:         'flex-start',
  },
  pillSm: {
    paddingHorizontal: spacing.sm,
    paddingVertical:   2,
  },
  label: {
    fontSize:   fontSize.sm,
    fontWeight: '700',
    letterSpacing: 0.4,
  },
  labelSm: {
    fontSize: fontSize.xs,
  },
});
