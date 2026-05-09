import React, { useMemo } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { useTheme } from '@/contexts/ThemeContext';
import { fontSize, spacing } from '@/constants/theme';

interface Props {
  content: string;
}

export function MarkdownView({ content }: Props) {
  const { colors, isDark } = useTheme();

  const mdStyles = useMemo(
    () =>
      StyleSheet.create({
        body: {
          color:          colors.textPri,
          fontSize:       fontSize.base,
          lineHeight:     fontSize.base * 1.75, // extra leading for dark bg
          backgroundColor: 'transparent',
        },
        heading1: {
          color:        colors.textPri,
          fontSize:     fontSize.xl,
          fontWeight:   '700',
          marginTop:    spacing.lg,
          marginBottom: spacing.sm,
        },
        heading2: {
          color:        colors.textPri,
          fontSize:     fontSize.lg,
          fontWeight:   '700',
          marginTop:    spacing.lg,
          marginBottom: spacing.xs,
        },
        heading3: {
          color:        colors.textSec,
          fontSize:     fontSize.base,
          fontWeight:   '700',
          marginTop:    spacing.md,
          marginBottom: spacing.xs,
        },
        strong: {
          color:      colors.textPri,
          fontWeight: '700',
        },
        em: {
          color:      colors.textSec,
          fontStyle:  'italic',
        },
        blockquote: {
          backgroundColor: colors.surface2,
          borderRadius:    4,
          paddingHorizontal: spacing.md,
          paddingVertical:   spacing.sm,
          marginVertical:    spacing.sm,
        },
        code_inline: {
          backgroundColor: colors.surface2,
          color:           colors.accent,
          fontSize:        fontSize.sm,
          borderRadius:    4,
          paddingHorizontal: 4,
        },
        fence: {
          backgroundColor: colors.surface2,
          borderRadius:    8,
          padding:         spacing.md,
          marginVertical:  spacing.sm,
        },
        code_block: {
          backgroundColor: colors.surface2,
          borderRadius:    8,
          padding:         spacing.md,
          marginVertical:  spacing.sm,
          fontSize:        fontSize.sm,
          color:           colors.textSec,
        },
        hr: {
          backgroundColor: colors.border,
          height:          1,
          marginVertical:  spacing.lg,
        },
        bullet_list: {
          marginVertical: spacing.xs,
        },
        list_item: {
          marginBottom: spacing.xs,
        },
        table: {
          borderWidth:  1,
          borderColor:  colors.border,
          borderRadius: 8,
          overflow:     'hidden',
          marginVertical: spacing.sm,
        },
        thead: {
          backgroundColor: colors.surface2,
        },
        th: {
          color:           colors.textSec,
          fontWeight:      '700',
          fontSize:        fontSize.xs,
          paddingVertical: spacing.sm,
          paddingHorizontal: spacing.md,
        },
        td: {
          color:           colors.textPri,
          fontSize:        fontSize.sm,
          paddingVertical: spacing.xs + 2,
          paddingHorizontal: spacing.md,
        },
        tr: {
          borderBottomWidth: 1,
          borderColor:       colors.border,
        },
      }),
    [colors, isDark],
  );

  return (
    <ScrollView
      style={styles.scrollView}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <Markdown style={mdStyles}>{content}</Markdown>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    flex: 1,
  },
  content: {
    paddingHorizontal: spacing.base,
    paddingBottom:     spacing.xxl,
  },
});
