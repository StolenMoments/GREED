import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { router, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useInfiniteAnalyses } from '@/api/analyses';
import { useTheme } from '@/contexts/ThemeContext';
import { useTablet } from '@/hooks/useTablet';
import { spacing, fontSize, radius } from '@/constants/theme';
import { AnalysisCard } from '@/components/AnalysisCard';
import { FilterBar } from '@/components/FilterBar';
import { SkeletonCard } from '@/components/SkeletonCard';
import { AnalysisDetailPanel } from '@/components/AnalysisDetailPanel';
import { apiKeyStorage } from '@/api/client';
import type { AnalysisItem, Judgment } from '@/api/types';

type Filter = Judgment | null;

export default function AnalysesScreen() {
  const { colors } = useTheme();
  const isTablet = useTablet();
  const params = useLocalSearchParams<{ ticker?: string }>();

  const [filter, setFilter] = useState<Filter>(null);
  const [search, setSearch] = useState(params.ticker ?? '');
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    if (params.ticker) {
      setSearch(params.ticker);
      setFilter(null);
    }
  }, [params.ticker]);

  const querySearch = search.trim();
  const { data, isPending, isRefetching, isFetchingNextPage, hasNextPage, fetchNextPage, refetch } =
    useInfiniteAnalyses({ judgment: filter, q: querySearch });

  const items = useMemo(
    () => data?.pages.flatMap((p) => p.items) ?? [],
    [data],
  );

  const handleCardPress = useCallback(
    (item: AnalysisItem) => {
      if (isTablet) {
        setSelectedId(item.id);
      } else {
        router.push(`/analysis/${item.id}`);
      }
    },
    [isTablet],
  );

  const handleEndReached = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  async function resetKey() {
    await apiKeyStorage.delete();
    router.replace('/setup');
  }

  const skeletons = [0, 1, 2, 3, 4];

  const ListFooter = isFetchingNextPage ? (
    <ActivityIndicator
      color={colors.accent}
      style={{ paddingVertical: spacing.lg }}
    />
  ) : null;

  const EmptyComponent = !isPending ? (
    <View style={styles.empty}>
      <Text style={[styles.emptyTitle, { color: colors.textSec }]}>
        해당 조건의 분석이 없습니다
      </Text>
      {(filter || querySearch) && (
        <Pressable
          onPress={() => { setFilter(null); setSearch(''); }}
          style={[styles.resetBtn, { borderColor: colors.border }]}
        >
          <Text style={{ color: colors.accent, fontSize: fontSize.sm }}>
            필터 초기화
          </Text>
        </Pressable>
      )}
    </View>
  ) : null;

  const listContent = (
    <FlatList
      style={{ flex: 1 }}
      data={isPending ? [] : items}
      keyExtractor={(item) => String(item.id)}
      renderItem={({ item }) => (
        <AnalysisCard
          item={item}
          onPress={() => handleCardPress(item)}
          selected={isTablet && selectedId === item.id}
        />
      )}
      ListHeaderComponent={
        isPending ? (
          <View style={styles.skeletons}>
            {skeletons.map((i) => <SkeletonCard key={i} />)}
          </View>
        ) : null
      }
      ListFooterComponent={ListFooter}
      ListEmptyComponent={EmptyComponent}
      ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
      contentContainerStyle={[styles.list, { flexGrow: 1 }]}
      onEndReached={handleEndReached}
      onEndReachedThreshold={0.5}
      refreshControl={
        <RefreshControl
          refreshing={isRefetching}
          onRefresh={refetch}
          tintColor={colors.accent}
        />
      }
      showsVerticalScrollIndicator={false}
    />
  );

  return (
    <View style={[styles.root, { backgroundColor: colors.bg }]}>
      {/* Top bar */}
      <View style={[styles.topBar, { backgroundColor: colors.bg, borderBottomColor: colors.border }]}>
        <View style={[styles.searchRow, { backgroundColor: colors.surface1, borderColor: colors.border }]}>
          <Ionicons name="search" size={16} color={colors.textTer} />
          <TextInput
            style={[styles.searchInput, { color: colors.textPri }]}
            placeholder="종목명, 초성, 티커 검색"
            placeholderTextColor={colors.textTer}
            value={search}
            onChangeText={setSearch}
            autoCapitalize="none"
            autoCorrect={false}
            clearButtonMode="while-editing"
            returnKeyType="search"
          />
          {search.length > 0 && (
            <Pressable onPress={() => setSearch('')} hitSlop={8}>
              <Ionicons name="close-circle" size={16} color={colors.textTer} />
            </Pressable>
          )}
        </View>
        <Pressable onPress={resetKey} hitSlop={8} style={styles.keyBtn}>
          <Ionicons name="key-outline" size={20} color={colors.textTer} />
        </Pressable>
      </View>

      <FilterBar value={filter} onChange={setFilter} />

      {isTablet ? (
        <View style={styles.split}>
          <View style={[styles.splitLeft, { borderRightColor: colors.border }]}>
            {listContent}
          </View>
          <View style={styles.splitRight}>
            {selectedId ? (
              <AnalysisDetailPanel id={selectedId} />
            ) : (
              <View style={styles.empty}>
                <Text style={[styles.emptyTitle, { color: colors.textTer }]}>
                  목록에서 분석을 선택하세요
                </Text>
              </View>
            )}
          </View>
        </View>
      ) : (
        listContent
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  topBar: {
    flexDirection:     'row',
    alignItems:        'center',
    gap:               spacing.sm,
    paddingHorizontal: spacing.base,
    paddingVertical:   spacing.sm,
    borderBottomWidth: 1,
  },
  searchRow: {
    flex:              1,
    flexDirection:     'row',
    alignItems:        'center',
    gap:               spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical:   spacing.sm,
    borderRadius:      radius.md,
    borderWidth:       1,
  },
  searchInput: {
    flex:       1,
    fontSize:   fontSize.sm,
    padding:    0,
  },
  keyBtn: {
    padding: spacing.xs,
  },
  list: {
    padding: spacing.base,
    gap:     spacing.sm,
  },
  skeletons: {
    gap: spacing.sm,
  },
  empty: {
    flex:           1,
    alignItems:     'center',
    justifyContent: 'center',
    gap:            spacing.md,
    paddingVertical: spacing.xxl,
  },
  emptyTitle: {
    fontSize: fontSize.base,
  },
  resetBtn: {
    borderWidth:       1,
    borderRadius:      radius.full,
    paddingHorizontal: spacing.base,
    paddingVertical:   spacing.sm,
  },
  split: {
    flex:          1,
    flexDirection: 'row',
  },
  splitLeft: {
    width:           360,
    borderRightWidth: 1,
  },
  splitRight: {
    flex: 1,
  },
});
