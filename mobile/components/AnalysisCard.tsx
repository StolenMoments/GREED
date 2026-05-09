import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { spacing, fontSize, radius } from '@/constants/theme';
import { JudgmentBadge } from './JudgmentBadge';
import { MetaTag } from './MetaTag';
import { formatRelativeTime } from '@/utils/time';
import type { AnalysisItem } from '@/api/types';

interface Props {
  item: AnalysisItem;
  onPress: () => void;
  selected?: boolean;
}

export function AnalysisCard({ item, onPress, selected = false }: Props) {
  const { colors, isDark } = useTheme();

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: selected
            ? (isDark ? colors.surface2 : colors.surface1)
            : colors.surface1,
          borderColor: selected ? colors.accent : colors.border,
        },
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.header}>
        <View style={styles.nameRow}>
          <Text style={[styles.name, { color: colors.textPri }]} numberOfLines={1}>
            {item.name}
          </Text>
          <Text style={[styles.ticker, { color: colors.textTer }]}>
            {item.ticker}
          </Text>
        </View>
        <JudgmentBadge judgment={item.judgment} size="sm" />
      </View>

      <View style={styles.tags}>
        <MetaTag label="추세" value={item.trend} />
        <MetaTag label="구름" value={item.cloud_position} />
        <MetaTag label="MA" value={item.ma_alignment} />
      </View>

      <Text style={[styles.time, { color: colors.textTer }]}>
        {formatRelativeTime(item.created_at)}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius:    radius.lg,
    borderWidth:     1,
    padding:         spacing.base,
    gap:             spacing.sm,
  },
  pressed: {
    opacity: 0.75,
  },
  header: {
    flexDirection:  'row',
    alignItems:     'flex-start',
    justifyContent: 'space-between',
    gap:            spacing.sm,
  },
  nameRow: {
    flex:     1,
    gap:      2,
  },
  name: {
    fontSize:   fontSize.base,
    fontWeight: '700',
  },
  ticker: {
    fontSize:      fontSize.xs,
    fontWeight:    '500',
    letterSpacing: 0.5,
  },
  tags: {
    flexDirection: 'row',
    flexWrap:      'wrap',
    gap:           spacing.xs,
  },
  time: {
    fontSize: fontSize.xs,
  },
});
