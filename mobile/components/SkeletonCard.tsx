import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { spacing, radius } from '@/constants/theme';

function Shimmer({ width, height }: { width: number | `${number}%`; height: number }) {
  const { colors } = useTheme();
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(anim, { toValue: 1, duration: 900, useNativeDriver: true }),
        Animated.timing(anim, { toValue: 0, duration: 900, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [anim]);

  const opacity = anim.interpolate({ inputRange: [0, 1], outputRange: [0.4, 0.8] });

  return (
    <Animated.View
      style={[
        styles.shimmer,
        { width, height, backgroundColor: colors.surface3, opacity },
      ]}
    />
  );
}

export function SkeletonCard() {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.surface1, borderColor: colors.border }]}>
      <View style={styles.header}>
        <View style={styles.nameBlock}>
          <Shimmer width="60%" height={16} />
          <Shimmer width="25%" height={12} />
        </View>
        <Shimmer width={44} height={24} />
      </View>
      <View style={styles.tags}>
        <Shimmer width={60} height={22} />
        <Shimmer width={70} height={22} />
        <Shimmer width={80} height={22} />
      </View>
      <Shimmer width="30%" height={11} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth:  1,
    padding:      spacing.base,
    gap:          spacing.sm,
  },
  header: {
    flexDirection:  'row',
    justifyContent: 'space-between',
    alignItems:     'flex-start',
  },
  nameBlock: {
    gap: spacing.xs,
    flex: 1,
  },
  shimmer: {
    borderRadius: radius.sm,
  },
  tags: {
    flexDirection: 'row',
    gap:           spacing.xs,
  },
});
