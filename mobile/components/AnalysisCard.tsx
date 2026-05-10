import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { spacing, fontSize, radius, palette } from '@/constants/theme';
import { JudgmentBadge } from './JudgmentBadge';
import { MetaTag } from './MetaTag';
import { formatRelativeTime } from '@/utils/time';
import type { AnalysisItem } from '@/api/types';

interface Props {
  item: AnalysisItem;
  onPress: () => void;
  selected?: boolean;
}

function formatPrice(price: number | null, priceMax: number | null): string | null {
  if (price == null) return null;
  const fmt = (n: number) => n.toLocaleString('ko-KR');
  return priceMax != null ? `${fmt(price)}~${fmt(priceMax)}` : fmt(price);
}

function calcPct(current: number, base: number): string {
  const pct = ((current - base) / base) * 100;
  return (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
}

function getSignalColor(value: string, isDark: boolean): string | undefined {
  const positive = ['상승', '구름 위', '정배열'];
  const neutral = ['횡보', '구름 안', '혼조'];
  const negative = ['하락', '구름 아래', '역배열'];

  if (positive.includes(value)) return isDark ? palette.buy : palette.buyLight;
  if (neutral.includes(value)) return isDark ? palette.hold : palette.holdLight;
  if (negative.includes(value)) return isDark ? palette.sell : palette.sellLight;
  return undefined;
}

export function AnalysisCard({ item, onPress, selected = false }: Props) {
  const { colors, isDark } = useTheme();

  const entryStr  = formatPrice(item.entry_price,  item.entry_price_max);
  const targetStr = formatPrice(item.target_price,  item.target_price_max);
  const stopStr   = formatPrice(item.stop_loss,     item.stop_loss_max);
  const hasPrices = entryStr != null || targetStr != null || stopStr != null;

  const currentPrice = item.current_price;
  const pctFromEntry =
    currentPrice != null && item.entry_price != null
      ? calcPct(currentPrice, item.entry_price)
      : null;
  const pctIsPositive = pctFromEntry != null && pctFromEntry.startsWith('+');

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
          {currentPrice != null && (
            <View style={styles.currentPriceRow}>
              <Text style={[styles.currentPrice, { color: colors.textPri }]}>
                {currentPrice.toLocaleString('ko-KR')}
              </Text>
              {pctFromEntry != null && (
                <Text style={[styles.pct, { color: pctIsPositive ? (isDark ? palette.buy : palette.buyLight) : (isDark ? palette.sell : palette.sellLight) }]}>
                  {pctFromEntry}
                </Text>
              )}
            </View>
          )}
        </View>
        <JudgmentBadge judgment={item.judgment} size="sm" />
      </View>

      <View style={styles.tags}>
        <MetaTag label="추세" value={item.trend} valueColor={getSignalColor(item.trend, isDark)} />
        <MetaTag label="구름" value={item.cloud_position} valueColor={getSignalColor(item.cloud_position, isDark)} />
        <MetaTag label="MA" value={item.ma_alignment} valueColor={getSignalColor(item.ma_alignment, isDark)} />
      </View>

      {hasPrices && (
        <View style={[styles.priceSection, { borderTopColor: colors.border }]}>
          {entryStr != null && (
            <View style={styles.priceItem}>
              <Text style={[styles.priceLabel, { color: colors.textTer }]}>진입</Text>
              <Text style={[styles.priceValue, { color: isDark ? palette.hold : palette.holdLight }]}>{entryStr}</Text>
            </View>
          )}
          {targetStr != null && (
            <View style={styles.priceItem}>
              <Text style={[styles.priceLabel, { color: colors.textTer }]}>목표</Text>
              <Text style={[styles.priceValue, { color: isDark ? palette.buy : palette.buyLight }]}>{targetStr}</Text>
            </View>
          )}
          {stopStr != null && (
            <View style={styles.priceItem}>
              <Text style={[styles.priceLabel, { color: colors.textTer }]}>손절</Text>
              <Text style={[styles.priceValue, { color: isDark ? palette.sell : palette.sellLight }]}>{stopStr}</Text>
            </View>
          )}
        </View>
      )}

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
  currentPriceRow: {
    flexDirection: 'row',
    alignItems:    'baseline',
    gap:           spacing.xs,
    marginTop:     2,
  },
  currentPrice: {
    fontSize:   fontSize.sm,
    fontWeight: '600',
  },
  pct: {
    fontSize:   fontSize.xs,
    fontWeight: '600',
  },
  tags: {
    flexDirection: 'row',
    flexWrap:      'wrap',
    gap:           spacing.xs,
  },
  priceSection: {
    flexDirection:  'row',
    flexWrap:       'wrap',
    gap:            spacing.md,
    paddingTop:     spacing.sm,
    marginTop:      spacing.xs,
    borderTopWidth: 1,
  },
  priceItem: {
    flexDirection: 'column',
    gap:           2,
  },
  priceLabel: {
    fontSize:      fontSize.xs,
    fontWeight:    '500',
    letterSpacing: 0.4,
    textTransform: 'uppercase' as const,
  },
  priceValue: {
    fontSize:   fontSize.base,
    fontWeight: '700',
  },
  time: {
    fontSize: fontSize.xs,
  },
});
