import React, { useMemo } from 'react';
import { Linking, StyleSheet } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { useTheme } from 'tamagui';
import { typography } from '@/constants/typography';

type CMarkdownProps = {
  children: string;
};

export const CMarkdown: React.FC<CMarkdownProps> = ({ children }) => {
  const theme = useTheme();

  const markdownStyle = useMemo<StyleSheet.NamedStyles<any>>(
    () => ({
      body: {
        color: theme.color11.val,
        fontSize: typography.body.fontSize,
        lineHeight: typography.body.lineHeight,
      },
      heading1: {
        color: theme.color12.val,
        fontSize: typography.markdownH1.fontSize,
        fontWeight: typography.markdownH1.fontWeight,
        lineHeight: typography.markdownH1.lineHeight,
        marginBottom: 12,
      },
      heading2: {
        color: theme.color12.val,
        fontSize: typography.markdownH2.fontSize,
        fontWeight: typography.markdownH2.fontWeight,
        lineHeight: typography.markdownH2.lineHeight,
        marginBottom: 10,
      },
      heading3: {
        color: theme.color12.val,
        fontSize: typography.markdownH3.fontSize,
        fontWeight: typography.markdownH3.fontWeight,
        lineHeight: typography.markdownH3.lineHeight,
        marginBottom: 8,
      },
      paragraph: {
        marginTop: 0,
        marginBottom: 10,
      },
      list_item: {
        marginBottom: 4,
      },
      strong: {
        fontWeight: '700',
      },
      em: {
        fontStyle: 'italic',
      },
      code_inline: {
        backgroundColor: theme.color3.val,
        color: theme.color12.val,
        borderRadius: 4,
        paddingHorizontal: 4,
        paddingVertical: 2,
      },
      code_block: {
        backgroundColor: theme.color2.val,
        borderRadius: 8,
        padding: 10,
        marginBottom: 10,
      },
      fence: {
        backgroundColor: theme.color2.val,
        borderRadius: 8,
        padding: 10,
        marginBottom: 10,
      },
      blockquote: {
        borderLeftWidth: 3,
        borderLeftColor: theme.color6.val,
        paddingLeft: 10,
        color: theme.color10.val,
        marginBottom: 10,
      },
      link: {
        color: theme.accent9.val,
        textDecorationLine: 'underline',
      },
      hr: {
        backgroundColor: theme.color4.val,
        height: 1,
        marginVertical: 12,
      },
    }),
    [theme],
  );

  return (
    <Markdown
      onLinkPress={(url) => {
        Linking.openURL(url);
        return true;
      }}
      style={markdownStyle}>
      {children}
    </Markdown>
  );
};
