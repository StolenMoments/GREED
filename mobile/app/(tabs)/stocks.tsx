import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useStocks } from '@/api/stocks';
import { useTheme } from '@/contexts/ThemeContext';
import { spacing, fontSize, radius, palette } from '@/constants/theme';
import { formatRelativeTime } from '@/utils/time';
import { extractChoseong } from '@/utils/korean';
import type { StockSummary } from '@/api/types';

function StockCard({ item, onPress }: { item: StockSummary; onPress: () => void }) {
  const { colors, isDark } = useTheme();
  const total = item.buy_count + item.hold_count + item.sell_count;

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: colors.surface1, borderColor: colors.border },
        pressed && { opacity: 0.75 },
      ]}
    >
      <View style={styles.cardHeader}>
        <View style={styles.nameBlock}>
          <Text style={[styles.stockName, { color: colors.textPri }]} numberOfLines={1}>
            {item.name}
          </Text>
          <Text style={[styles.ticker, { color: colors.textTer }]}>
            {item.ticker}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={colors.textTer} />
      </View>

      <View style={styles.counts}>
        <View style={[styles.countPill, { backgroundColor: isDark ? '#1A3D2B' : '#D0EDD9' }]}>
          <Text style={[styles.countNum, { color: isDark ? palette.buy : palette.buyLight }]}>
            {item.buy_count}
          </Text>
          <Text style={[styles.countLbl, { color: isDark ? palette.buy : palette.buyLight }]}>
            매수
          </Text>
        </View>
        <View style={[styles.countPill, { backgroundColor: isDark ? '#3A2D0A' : '#F5E8C0' }]}>
          <Text style={[styles.countNum, { color: isDark ? palette.hold : palette.holdLight }]}>
            {item.hold_count}
          </Text>
          <Text style={[styles.countLbl, { color: isDark ? palette.hold : palette.holdLight }]}>
            홀드
          </Text>
        </View>
        <View style={[styles.countPill, { backgroundColor: isDark ? '#3D1410' : '#F5D0CC' }]}>
          <Text style={[styles.countNum, { color: isDark ? palette.sell : palette.sellLight }]}>
            {item.sell_count}
          </Text>
          <Text style={[styles.countLbl, { color: isDark ? palette.sell : palette.sellLight }]}>
            매도
          </Text>
        </View>
        <Text style={[styles.total, { color: colors.textTer }]}>
          총 {total}회
        </Text>
      </View>

      <Text style={[styles.latest, { color: colors.textTer }]}>
        최근 분석: {formatRelativeTime(item.latest_at)}
      </Text>
    </Pressable>
  );
}

export default function StocksScreen() {
  const { colors } = useTheme();
  const [search, setSearch] = useState('');
  const { data, isPending, isRefetching, refetch } = useStocks();

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    if (!q) return data;
    return data.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.ticker.toLowerCase().includes(q) ||
        extractChoseong(s.name).includes(q),
    );
  }, [data, search]);

  function handleStockPress(ticker: string) {
    router.push({ pathname: '/(tabs)/', params: { ticker } });
  }

  return (
    <View style={[styles.root, { backgroundColor: colors.bg }]}>
      <View style={[styles.searchBar, { backgroundColor: colors.bg, borderBottomColor: colors.border }]}>
        <View style={[styles.searchRow, { backgroundColor: colors.surface1, borderColor: colors.border }]}>
          <Ionicons name="search" size={16} color={colors.textTer} />
          <TextInput
            style={[styles.searchInput, { color: colors.textPri }]}
            placeholder="종목명, 티커 검색"
            placeholderTextColor={colors.textTer}
            value={search}
            onChangeText={setSearch}
            autoCapitalize="none"
            autoCorrect={false}
            clearButtonMode="while-editing"
          />
          {search.length > 0 && (
            <Pressable onPress={() => setSearch('')} hitSlop={8}>
              <Ionicons name="close-circle" size={16} color={colors.textTer} />
            </Pressable>
          )}
        </View>
      </View>

      {isPending ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(item) => item.ticker}
          renderItem={({ item }) => (
            <StockCard
              item={item}
              onPress={() => handleStockPress(item.ticker)}
            />
          )}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
          contentContainerStyle={[styles.list, { flexGrow: 1 }]}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={{ color: colors.textSec, fontSize: fontSize.base }}>
                {search ? '검색 결과가 없습니다' : '분석된 종목이 없습니다'}
              </Text>
            </View>
          }
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor={colors.accent}
            />
          }
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  searchBar: {
    paddingHorizontal: spacing.base,
    paddingVertical:   spacing.sm,
    borderBottomWidth: 1,
  },
  searchRow: {
    flexDirection:     'row',
    alignItems:        'center',
    gap:               spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical:   spacing.sm,
    borderRadius:      radius.md,
    borderWidth:       1,
  },
  searchInput: {
    flex:     1,
    fontSize: fontSize.sm,
    padding:  0,
  },
  center: {
    flex:           1,
    alignItems:     'center',
    justifyContent: 'center',
  },
  list: {
    padding: spacing.base,
    gap:     spacing.sm,
  },
  card: {
    borderRadius: radius.lg,
    borderWidth:  1,
    padding:      spacing.base,
    gap:          spacing.sm,
  },
  cardHeader: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'space-between',
  },
  nameBlock: {
    flex: 1,
    gap:  2,
  },
  stockName: {
    fontSize:   fontSize.base,
    fontWeight: '700',
  },
  ticker: {
    fontSize:      fontSize.xs,
    fontWeight:    '500',
    letterSpacing: 0.5,
  },
  counts: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           spacing.xs,
    flexWrap:      'wrap',
  },
  countPill: {
    flexDirection:     'row',
    alignItems:        'center',
    gap:               3,
    paddingHorizontal: spacing.sm,
    paddingVertical:   3,
    borderRadius:      radius.full,
  },
  countNum: {
    fontSize:   fontSize.sm,
    fontWeight: '700',
  },
  countLbl: {
    fontSize: fontSize.xs,
  },
  total: {
    fontSize:  fontSize.xs,
    marginLeft: spacing.xs,
  },
  latest: {
    fontSize: fontSize.xs,
  },
});
