import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { palette, spacing, fontSize, radius } from '@/constants/theme';
import type { Judgment } from '@/api/types';

type Filter = Judgment | null;

const filters: { label: string; value: Filter }[] = [
  { label: '전체', value: null },
  { label: '매수', value: '매수' },
  { label: '홀드', value: '홀드' },
  { label: '매도', value: '매도' },
];

interface Props {
  value: Filter;
  onChange: (value: Filter) => void;
}

export function FilterBar({ value, onChange }: Props) {
  const { colors, isDark } = useTheme();

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
    >
      {filters.map((f) => {
        const active = f.value === value;
        return (
          <Pressable
            key={f.label}
            onPress={() => onChange(f.value)}
            style={({ pressed }) => [
              styles.chip,
              {
                backgroundColor: active
                  ? (isDark ? palette.dark.accent : palette.light.accent)
                  : colors.surface2,
                borderColor: active
                  ? (isDark ? palette.dark.accent : palette.light.accent)
                  : colors.border,
              },
              pressed && styles.pressed,
            ]}
          >
            <Text
              style={[
                styles.label,
                {
                  color: active
                    ? (isDark ? '#1A1000' : '#FFFFFF')
                    : colors.textSec,
                  fontWeight: active ? '700' : '500',
                },
              ]}
            >
              {f.label}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap:           spacing.sm,
    paddingHorizontal: spacing.base,
    paddingVertical:   spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical:   spacing.xs + 2,
    borderRadius:      radius.full,
    borderWidth:       1,
  },
  label: {
    fontSize: fontSize.sm,
  },
  pressed: {
    opacity: 0.7,
  },
});
