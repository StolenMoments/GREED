import type { DailyRallyRuleStat } from '../api/backtest';

const FEATURE_LABELS: Record<string, string> = {
  ret_20d: '최근 20거래일 수익률',
  ret_60d: '최근 60거래일 수익률',
  volume_ratio_20d: '거래량 20일 평균 대비',
  trading_value_ratio_20d: '거래대금 20일 평균 대비',
  close_to_20d_high: '20일 고점 대비 현재가',
  close_to_60d_high: '60일 고점 대비 현재가',
  close_to_20d_low: '20일 저점 대비 현재가',
  range_pct: '당일 고저 변동폭',
  rsi14: 'RSI 14',
  atr_pct_14: 'ATR 14 / 종가',
  ma5_gt_ma20: '5일선이 20일선 위',
  ma20_gt_ma60: '20일선이 60일선 위',
  ma60_up: '60일선 상승',
  weekly_close_gt_ma20: '주봉 종가가 20주선 위',
  weekly_ma5_gt_ma20: '주봉 5주선이 20주선 위',
  weekly_cloud_position: '주봉 일목 구름 위치',
  weekly_span2_breakout_recent_4w: '최근 4주 안에 주봉 선행스팬2 돌파',
};

function percentThreshold(feature: string, value: number): string {
  if (
    feature.startsWith('ret_') ||
    feature.startsWith('close_to_') ||
    feature === 'range_pct' ||
    feature === 'atr_pct_14'
  ) {
    return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(0)}%`;
  }
  return value.toFixed(value % 1 === 0 ? 0 : 2);
}

function translateAtomicRule(rawRule: string): string {
  const threshold = rawRule.match(/^([^>=]+)>=(.+)$/);
  if (threshold) {
    const [, feature, rawValue] = threshold;
    const value = Number(rawValue);
    const label = FEATURE_LABELS[feature] ?? feature;
    if (feature.endsWith('_ratio_20d')) {
      return `${label} ${value.toFixed(value % 1 === 0 ? 0 : 1)}배 이상`;
    }
    return `${label} ${percentThreshold(feature, value)} 이상`;
  }

  const equality = rawRule.match(/^([^=]+)==(.+)$/);
  if (equality) {
    const [, feature, value] = equality;
    const label = FEATURE_LABELS[feature] ?? feature;
    if (value === 'True') return label;
    if (feature === 'weekly_cloud_position' && value === 'above_cloud') {
      return '주봉 종가가 구름대 위';
    }
    return `${label}: ${value}`;
  }

  return rawRule;
}

export function translateDailyRallyRule(rule: string): string {
  return rule.split('&').map(translateAtomicRule).join(' + ');
}

export function explainDailyRallyRule(rule: DailyRallyRuleStat): string {
  const precision = (rule.precision * 100).toFixed(1);
  const baseRate = (rule.base_rate * 100).toFixed(1);
  return `${rule.total_matches.toLocaleString('ko-KR')}건 중 ${rule.support.toLocaleString(
    'ko-KR',
  )}건이 20거래일 내 +40% 급등했습니다. 전체 기준 ${baseRate}% 대비 이 조건은 ${precision}%입니다.`;
}

export function classifyDailyRallyRule(rule: DailyRallyRuleStat): string {
  if (rule.lift >= 3) return '강한 반복 패턴';
  if (rule.lift >= 2) return '의미 있는 반복 패턴';
  if (rule.lift >= 1.2) return '약한 반복 패턴';
  return '전체 평균과 큰 차이 없음';
}
