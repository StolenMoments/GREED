import type { AnalysisModel } from '../types';

export const MODEL_OPTIONS = [
  { id: 'claude' as AnalysisModel, label: 'Claude', provider: 'Anthropic' },
  { id: 'codex' as AnalysisModel, label: 'Codex', provider: 'OpenAI' },
  { id: 'gemini' as AnalysisModel, label: 'Gemini', provider: 'Google' },
] as const;

const MODEL_ALIASES: Record<string, AnalysisModel> = {
  claude: 'claude',
  codex: 'codex',
  'codex-cli': 'codex',
  gemini: 'gemini',
  'gemini-cli': 'gemini',
};

export function toAnalysisModel(value: string | null | undefined): AnalysisModel {
  return value ? (MODEL_ALIASES[value.toLowerCase()] ?? 'claude') : 'claude';
}
