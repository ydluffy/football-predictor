import { teamNameZh } from "@/lib/zh";

// 市场信号行（CSV 口径）与数据库 fixtures 的匹配工具。
// 与 /api/market-intel 的本地 CSV 匹配规则保持一致：主客队名候选集 + 北京时间开赛日期。

export type MatchableFixture = {
  fixture_id: number;
  utc_date?: string | null;
  home_team_name?: string | null;
  home_team_name_zh?: string | null;
  away_team_name?: string | null;
  away_team_name_zh?: string | null;
};

export function normalizeMarketName(s?: string | null) {
  return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

export function shanghaiMarketDate(iso?: string | null) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function marketCandidateNames(fixture: MatchableFixture) {
  return {
    home: new Set(
      [
        fixture.home_team_name,
        fixture.home_team_name_zh,
        teamNameZh(fixture.home_team_name),
        teamNameZh(fixture.home_team_name_zh),
      ]
        .map(normalizeMarketName)
        .filter(Boolean),
    ),
    away: new Set(
      [
        fixture.away_team_name,
        fixture.away_team_name_zh,
        teamNameZh(fixture.away_team_name),
        teamNameZh(fixture.away_team_name_zh),
      ]
        .map(normalizeMarketName)
        .filter(Boolean),
    ),
  };
}

export function isSameMarketFixture(
  fixture: MatchableFixture,
  homeTeam: string,
  awayTeam: string,
  kickoffAt: string,
) {
  const names = marketCandidateNames(fixture);
  const home = normalizeMarketName(homeTeam);
  const away = normalizeMarketName(awayTeam);
  const kickoffDate = shanghaiMarketDate(kickoffAt);
  const fixtureDate = shanghaiMarketDate(fixture.utc_date);
  return names.home.has(home) && names.away.has(away) && kickoffDate != null && kickoffDate === fixtureDate;
}
