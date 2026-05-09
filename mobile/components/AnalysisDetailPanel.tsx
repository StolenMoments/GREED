import React from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useAnalysis } from '@/api/analyses';
import { useTheme } from '@/contexts/ThemeContext';
import { spacing, fontSize } from '@/constants/theme';
import { JudgmentBadge } from './JudgmentBadge';
import { MetaTag } from './MetaTag';
import { MarkdownView } from './MarkdownView';
import { formatRelativeTime } from '@/utils/time';

interface Props {
  id: number;
}

export function AnalysisDetailPanel({ id }: Props) {
  const { data, isPending, isError } = useAnalysis(id);
  const { colors } = useTheme();

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
  time: {
    fontSize: fontSize.xs,
  },
});
