import { buildDailyRallyCandidatesParams } from './backtest';

const emptyParams = buildDailyRallyCandidatesParams();

if (Object.keys(emptyParams).length !== 0) {
  throw new Error('Daily Rally candidates params should be empty by default');
}

const buyParams = buildDailyRallyCandidatesParams({ tier: 'buy', limit: 10 });

if (buyParams.tier !== 'buy' || buyParams.limit !== 10) {
  throw new Error('Daily Rally candidates params should include tier and limit when provided');
}
