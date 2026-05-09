import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useTheme } from '@/contexts/ThemeContext';
import { AnalysisDetailPanel } from '@/components/AnalysisDetailPanel';

export default function AnalysisDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();

  return (
    <View style={[styles.root, { backgroundColor: colors.bg }]}>
      <AnalysisDetailPanel id={Number(id)} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
});
