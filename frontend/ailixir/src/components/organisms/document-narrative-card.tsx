/**
 * Document Narrative card — surfaces the rich clinical narrative the new
 * Gemini-multimodal pipeline produced for a document.
 *
 * This is a SEPARATE card from `OcrTextCard`, which renders the raw OCR
 * text from the legacy Document-AI pipeline. The two pipelines populate
 * different fields on the same Extraction record:
 *
 *   OcrTextCard           ← uses extraction.raw_text          (legacy)
 *   DocumentNarrativeCard ← uses extraction.episode_body      (new LLM)
 *
 * Each card auto-hides if its field is absent, so a document extracted by
 * either pipeline shows the right card without explicit branching at the
 * detail-screen level.
 *
 * Display states:
 *   - loading      → caption "Loading narrative…"
 *   - error        → caption explaining what likely happened
 *   - empty/absent → nothing rendered (parent controls visibility)
 *   - populated    → header chips (doc_type, doc_date, char count) +
 *                    scrollable narrative body in a readable serif/sans
 *                    rather than monospace (this is prose, not OCR)
 */

import { CText } from '@/components/atoms';
import { ExtractionResponse } from '@/hooks/useDocumentExtraction';
import React from 'react';
import { ScrollView, XStack, YStack } from 'tamagui';

interface DocumentNarrativeCardProps {
  extraction: ExtractionResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function DocumentNarrativeCard({ extraction, isLoading, isError }: DocumentNarrativeCardProps) {
  // Auto-hide when there's nothing to show. The parent screen always renders
  // this card, but a doc extracted by the legacy OCR pipeline won't have an
  // episode_body and shouldn't display an empty card with chips and headers.
  const hasNarrative = !!extraction?.episode_body;
  if (!isLoading && !isError && !hasNarrative) {
    return null;
  }

  return (
    <YStack gap={12} bg="$color1" p={16} borderWidth={1} borderColor="$color3" style={{ borderRadius: 20 }}>
      <XStack items="center" justify="space-between" gap={8} flexWrap="wrap">
        <CText variant="h2" color="$color11">
          Document Narrative
        </CText>
        <NarrativeChips extraction={extraction} />
      </XStack>

      {isLoading && (
        <CText variant="caption" color="$color9">
          Loading narrative…
        </CText>
      )}

      {isError && (
        <CText variant="caption" color="$red11">
          Could not load the document narrative. The extraction may still be in progress, or this document predates the new analysis pipeline.
        </CText>
      )}

      {!isLoading && !isError && extraction?.episode_body && (
        <ScrollView style={{ maxHeight: 360, borderRadius: 12 }} bg="$color2" p={12} showsVerticalScrollIndicator>
          {/*
            Narrative prose — render in the body font, not Menlo. Unlike the
            OCR card (which preserves original document columns via monospace),
            this is a single LLM-authored paragraph and reads better in the
            normal body face.
          */}
          <CText variant="caption" color="$color12" selectable style={{ lineHeight: 20 }}>
            {extraction.episode_body}
          </CText>
        </ScrollView>
      )}
    </YStack>
  );
}

function NarrativeChips({ extraction }: { extraction: ExtractionResponse | undefined }) {
  if (!extraction) {
    return null;
  }
  return (
    <XStack gap={6} flexWrap="wrap">
      {extraction.document_type && extraction.document_type !== 'Unknown' && <Chip label={extraction.document_type} />}
      {extraction.document_date && <Chip label={extraction.document_date} />}
      {typeof extraction.episode_body === 'string' && extraction.episode_body.length > 0 && <Chip label={`${extraction.episode_body.length.toLocaleString()} chars`} />}
    </XStack>
  );
}

function Chip({ label }: { label: string }) {
  return (
    <XStack px={8} py={2} bg="$color3" style={{ borderRadius: 999 }}>
      <CText variant="caption" color="$color11">
        {label}
      </CText>
    </XStack>
  );
}
