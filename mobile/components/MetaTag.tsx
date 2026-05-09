import React from 'react';
import { Text, View, StyleSheet } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { fontSize, spacing, radius } from '@/constants/theme';

interface Props {
  label: string;
  value: string;
  valueColor?: string;
}

export function MetaTag({ label, value, valueColor }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.tag, { backgroundColor: colors.surface2, borderColor: colors.border }]}>
      <Text style={[styles.lbl, { color: colors.textTer }]}>{label}</Text>
      <Text style={[styles.val, { color: valueColor ?? colors.textSec }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tag: {
    flexDirection:  'row',
    alignItems:     'center',
    gap:            4,
    paddingHorizontal: spacing.sm,
    paddingVertical:   3,
    borderRadius:   radius.sm,
    borderWidth:    1,
  },
  lbl: {
    fontSize: fontSize.xs,
  },
  val: {
    fontSize:   fontSize.xs,
    fontWeight: '600',
  },
});
