import React from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useAnalysis } from '@/api/analyses';
import { useTheme } from '@/contexts/ThemeContext';
import { spacing, fontSize, radius, palette } from '@/constants/theme';
import { JudgmentBadge } from './JudgmentBadge';
import { MetaTag } from './MetaTag';
import { MarkdownView } from './MarkdownView';
import { formatRelativeTime } from '@/utils/time';
import { parsePricesFromMarkdown } from '@/utils/parsePrice';
import { formatPrice } from '@/utils/formatPrice';

interface Props {
  id: number;
}

export function AnalysisDetailPanel({ id }: Props) {
  const { data, isPending, isError } = useAnalysis(id);
  const { colors, isDark } = useTheme();

  if (isPending) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  if (isError || !data) {
    return (
      <View style={styles.center}>
        <Text style={[styles.errorText, { color: colors.textSec }]}>
          분석을 불러오지 못했습니다.
        </Text>
      </View>
    );
  }

  const parsed = parsePricesFromMarkdown(data.markdown);
  const entryPrice  = data.entry_price  ?? parsed.entry_price;
  const entryMax    = data.entry_price_max  ?? parsed.entry_price_max;
  const targetPrice = data.target_price ?? parsed.target_price;
  const targetMax   = data.target_price_max ?? parsed.target_price_max;
  const stopLoss    = data.stop_loss    ?? parsed.stop_loss;
  const stopMax     = data.stop_loss_max    ?? parsed.stop_loss_max;

  const entryStr  = formatPrice(entryPrice,  entryMax);
  const targetStr = formatPrice(targetPrice, targetMax);
  const stopStr   = formatPrice(stopLoss,    stopMax);
  const hasPrices = entryStr != null || targetStr != null || stopStr != null;

  const currentPrice = data.current_price;
  const currentPriceDate = data.current_price_date;
  const pctFromEntry =
    currentPrice != null && entryPrice != null
      ? ((currentPrice - entryPrice) / entryPrice * 100)
      : null;
  const pctStr = pctFromEntry != null
    ? (pctFromEntry >= 0 ? '+' : '') + pctFromEntry.toFixed(1) + '%'
    : null;

  const entryBg  = isDark ? colors.surface2  : colors.surface2;
  const targetBg = isDark ? '#1A3D2B'        : '#D0EDD9';
  const stopBg   = isDark ? '#3D1410'        : '#F5D0CC';

  return (
    <View style={styles.container}>
      <View style={[styles.header, { borderBottomColor: colors.border }]}>
        <View style={styles.titleRow}>
          <View style={styles.nameBlock}>
            <Text style={[styles.name, { color: colors.textPri }]} numberOfLines={1}>
              {data.name}
            </Text>
            <Text style={[styles.ticker, { color: colors.textTer }]}>
              {data.ticker}
            </Text>
          </View>
          <JudgmentBadge judgment={data.judgment} />
        </View>

        <View style={styles.tagRow}>
          <MetaTag label="추세" value={data.trend} />
          <MetaTag label="구름" value={data.cloud_position} />
          <MetaTag label="MA" value={data.ma_alignment} />
        </View>

        {currentPrice != null && (
          <View style={styles.currentPriceBlock}>
            <View style={styles.currentPriceRow}>
              <Text style={[styles.currentPriceValue, { color: colors.textPri }]}>
                {currentPrice.toLocaleString('ko-KR')}
              </Text>
              {pctStr != null && (
                <Text style={[
                  styles.currentPricePct,
                  { color: pctFromEntry! >= 0 ? (isDark ? palette.buy : palette.buyLight) : (isDark ? palette.sell : palette.sellLight) },
                ]}>
                  {pctStr}
                </Text>
              )}
            </View>
            {currentPriceDate != null && (
              <Text style={[styles.currentPriceDate, { color: colors.textTer }]}>
                {currentPriceDate.slice(5).replace('-', '/')} 종가
              </Text>
            )}
          </View>
        )}

        {hasPrices && (
          <View style={styles.priceRow}>
            {entryStr != null && (
              <View style={[styles.pricePill, { backgroundColor: entryBg, borderColor: colors.border }]}>
                <Text style={[styles.pillLabel, { color: colors.textTer }]}>진입가</Text>
                <Text style={[styles.pillValue, { color: colors.textSec }]}>{entryStr}</Text>
              </View>
            )}
            {targetStr != null && (
              <View style={[styles.pricePill, { backgroundColor: targetBg, borderColor: targetBg }]}>
                <Text style={[styles.pillLabel, { color: isDark ? palette.buy : palette.buyLight }]}>목표가</Text>
                <Text style={[styles.pillValue, { color: isDark ? palette.buy : palette.buyLight }]}>{targetStr}</Text>
              </View>
            )}
            {stopStr != null && (
              <View style={[styles.pricePill, { backgroundColor: stopBg, borderColor: stopBg }]}>
                <Text style={[styles.pillLabel, { color: isDark ? palette.sell : palette.sellLight }]}>손절가</Text>
                <Text style={[styles.pillValue, { color: isDark ? palette.sell : palette.sellLight }]}>{stopStr}</Text>
              </View>
            )}
          </View>
        )}

        <Text style={[styles.time, { color: colors.textTer }]}>
          {formatRelativeTime(data.created_at)}
        </Text>
      </View>

      <MarkdownView content={data.markdown} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  center: {
    flex:           1,
    alignItems:     'center',
    justifyContent: 'center',
  },
  errorText: {
    fontSize: fontSize.base,
  },
  header: {
    padding:           spacing.base,
    gap:               spacing.sm,
    borderBottomWidth: 1,
  },
  titleRow: {
    flexDirection:  'row',
    alignItems:     'flex-start',
    justifyContent: 'space-between',
    gap:            spacing.sm,
  },
  nameBlock: {
    flex: 1,
    gap:  2,
  },
  name: {
    fontSize:   fontSize.xl,
    fontWeight: '700',
  },
  ticker: {
    fontSize:      fontSize.sm,
    fontWeight:    '500',
    letterSpacing: 0.5,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap:      'wrap',
    gap:           spacing.xs,
  },
  priceRow: {
    flexDirection: 'row',
    flexWrap:      'wrap',
    gap:           spacing.xs,
  },
  currentPriceBlock: {
    gap: 2,
  },
  currentPriceRow: {
    flexDirection: 'row',
    alignItems:    'baseline',
    gap:           spacing.xs,
  },
  currentPriceValue: {
    fontSize:   fontSize.xl,
    fontWeight: '700',
  },
  currentPricePct: {
    fontSize:   fontSize.sm,
    fontWeight: '600',
  },
  currentPriceDate: {
    fontSize: fontSize.xs,
  },
  pricePill: {
    flexDirection:     'row',
    alignItems:        'center',
    gap:               4,
    paddingHorizontal: spacing.sm,
    paddingVertical:   3,
    borderRadius:      radius.sm,
    borderWidth:       1,
  },
  pillLabel: {
    fontSize:   fontSize.xs,
    fontWeight: '500',
  },
  pillValue: {
    fontSize:   fontSize.xs,
    fontWeight: '700',
  },
  time: {
    fontSize: fontSize.xs,
  },
});
