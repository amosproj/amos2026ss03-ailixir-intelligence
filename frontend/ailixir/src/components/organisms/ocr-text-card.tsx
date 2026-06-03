/**
 * Debug card showing the raw OCR text extracted from a document.
 *
 * Rendered on the document detail screen when:
 *   - the user has enabled `debug.showOcrText` in Settings, AND
 *   - the document has reached status='extracted' (i.e. the pipeline ran
 *     to completion and the extraction record exists).
 *
 * Three display states:
 *   - loading      → centered caption "Loading OCR text…"
 *   - empty        → caption "No raw OCR text was captured for this
 *                    document." (older extractions, OR pipelines that
 *                    didn't save raw_text)
 *   - populated    → header chip(s) + scrollable monospace body
 *
 * The text body is rendered inside a fixed-height ScrollView so a long
 * report doesn't push the rest of the screen off. Wrapping is enabled so
 * very long lines don't require horizontal scroll — easier to read on
 * mobile than horizontal panning.
 */

import { CText } from '@/components/atoms';
import { ExtractionResponse } from '@/hooks/useDocumentExtraction';
import React from 'react';
import { ScrollView, XStack, YStack } from 'tamagui';

interface OcrTextCardProps {
  extraction: ExtractionResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function OcrTextCard({ extraction, isLoading, isError }: OcrTextCardProps) {
  return (
    <YStack gap={12} bg="$color1" p={16} borderWidth={1} borderColor="$color3" style={{ borderRadius: 20 }}>
      <XStack items="center" justify="space-between" gap={8} flexWrap="wrap">
        <CText variant="h2" color="$color11">
          OCR Text (debug)
        </CText>
        <OcrChips extraction={extraction} />
      </XStack>

      {isLoading && (
        <CText variant="caption" color="$color9">
          Loading OCR text…
        </CText>
      )}

      {isError && (
        <CText variant="caption" color="$red11">
          Could not load OCR text. The extraction may still be in progress, or the worker may not have persisted raw text for this document.
        </CText>
      )}

      {!isLoading && !isError && extraction && !extraction.raw_text && (
        <CText variant="caption" color="$color9">
          No raw OCR text was captured for this document. This is normal for extractions that ran before the raw-text feature shipped, or for documents whose OCR processor returned only structured
          fields.
        </CText>
      )}

      {!isLoading && !isError && extraction?.raw_text && (
        <ScrollView style={{ maxHeight: 320, borderRadius: 12 }} bg="$color2" p={12} showsVerticalScrollIndicator>
          {/*
            Using CText with a fixed-width font family so columns in the
            original document remain visually aligned. fontVariant tabular
            keeps numbers tidy in clinical reports (dates, patient IDs).
          */}
          <CText
            variant="caption"
            color="$color12"
            style={{
              fontFamily: 'Menlo',
              fontVariant: ['tabular-nums'],
              lineHeight: 18,
            }}>
            {extraction.raw_text}
          </CText>
        </ScrollView>
      )}
    </YStack>
  );
}

function OcrChips({ extraction }: { extraction: ExtractionResponse | undefined }) {
  if (!extraction) {
    return null;
  }
  return (
    <XStack gap={6} flexWrap="wrap">
      {typeof extraction.raw_text_chars === 'number' && extraction.raw_text_chars > 0 && <Chip label={`${extraction.raw_text_chars.toLocaleString()} chars`} />}
      {extraction.raw_text_truncated && <Chip label="truncated" tone="warning" />}
      {typeof extraction.confidence_score === 'number' && <Chip label={`conf ${(extraction.confidence_score * 100).toFixed(0)}%`} />}
    </XStack>
  );
}

function Chip({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'warning' }) {
  const bg = tone === 'warning' ? '$yellow2' : '$color3';
  const color = tone === 'warning' ? '$yellow11' : '$color11';
  return (
    <XStack px={8} py={2} bg={bg} style={{ borderRadius: 999 }}>
      <CText variant="caption" color={color}>
        {label}
      </CText>
    </XStack>
  );
}
