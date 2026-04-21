import type { ParsedField, ParsedMarkdown } from '../utils/parseMarkdown';

const fieldLabels: Record<ParsedField, string> = {
  judgment: '판정',
  trend: '추세',
  cloud_position: '구름대',
  ma_alignment: 'MA 배열',
};

const priceFormatter = new Intl.NumberFormat('ko-KR');

interface ParsedSummaryCardProps {
  parsed: ParsedMarkdown;
  showErrors?: boolean;
}

function ParsedSummaryCard({
  parsed,
  showErrors = false,
}: ParsedSummaryCardProps) {
  const failedFields = new Set(parsed.failed);

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-100">파싱 미리보기</h3>
        <span
          className={[
            'rounded-full border px-2.5 py-1 text-xs font-semibold',
            parsed.success
              ? 'border-emerald-300/35 bg-emerald-300/10 text-emerald-100'
              : 'border-rose-300/35 bg-rose-300/10 text-rose-100',
          ].join(' ')}
        >
          {parsed.success ? '완료' : '확인 필요'}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3">
        <SummaryItem
          failed={showErrors && failedFields.has('judgment')}
          label={fieldLabels.judgment}
          value={parsed.data.judgment}
        />
        <SummaryItem
          failed={showErrors && failedFields.has('trend')}
          label={fieldLabels.trend}
          value={parsed.data.trend}
        />
        <SummaryItem
          failed={showErrors && failedFields.has('cloud_position')}
          label={fieldLabels.cloud_position}
          value={parsed.data.cloud_position}
        />
        <SummaryItem
          failed={showErrors && failedFields.has('ma_alignment')}
          label={fieldLabels.ma_alignment}
          value={parsed.data.ma_alignment}
        />
        <SummaryItem label="진입가" value={formatPrice(parsed.data.entry_price)} />
        <SummaryItem label="목표가" value={formatPrice(parsed.data.target_price)} />
        <SummaryItem label="손절가" value={formatPrice(parsed.data.stop_loss)} />
      </dl>

      {showErrors && parsed.failed.length > 0 ? (
        <p className="mt-4 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs leading-5 text-rose-100">
          누락 필드: {parsed.failed.map((field) => fieldLabels[field]).join(', ')}
        </p>
      ) : null}
    </aside>
  );
}

function SummaryItem({
  failed = false,
  label,
  value,
}: {
  failed?: boolean;
  label: string;
  value?: string | null;
}) {
  return (
    <div
      className={[
        'rounded-md border px-3 py-2',
        failed
          ? 'border-rose-300/50 bg-rose-950/25'
          : 'border-slate-800 bg-slate-950/50',
      ].join(' ')}
    >
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 min-h-5 text-sm font-semibold text-slate-100">
        {value ?? '-'}
      </dd>
    </div>
  );
}

function formatPrice(value: number | null) {
  return value === null ? null : priceFormatter.format(value);
}

export default ParsedSummaryCard;
