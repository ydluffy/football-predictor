-- 市场信号情报表：把本地 movement / alignment 特征同步入库，让线上 Web 不依赖本地 artifacts
-- 数据来源：handicap_market_movement_latest.csv + inner_outer_market_alignment_latest.csv
-- 写入方：/api/automation/sync-market（由 run_controller_data_sync.py --stage market 调用）

create table if not exists public.fixture_market_intel (
  fixture_id bigint primary key,
  sales_day date null,
  movement jsonb null,
  alignment jsonb null,
  movement_captured_at timestamptz null,
  alignment_captured_at timestamptz null,
  source_note text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists fixture_market_intel_sales_day_idx
  on public.fixture_market_intel (sales_day);

drop trigger if exists fixture_market_intel_set_updated_at on public.fixture_market_intel;
create trigger fixture_market_intel_set_updated_at
before update on public.fixture_market_intel
for each row execute function public.set_updated_at();

alter table public.fixture_market_intel enable row level security;

-- 变盘历史明细表：Nowscore /handle/odds.aspx?cmd=ypchange 的“近 5 次变化记录”事件流。
-- 数据来源：data/external/nowscore/snapshots/<sales_day>_<stamp>/price_changes.csv
-- 写入方：/api/automation/sync-market（由 run_controller_data_sync.py --stage market 调用）
-- 每次抓取都会重放同样的记录，所以按“事件本身”去重：
-- change_key 由写入方按 odds_id + 盘口/水位原文 + 变化时间原文生成。
-- handicap 沿用页面符号约定（负数 = 主队让球），与 outer_market.csv 的 home_handicap 一致。
-- sequence 是「最近一次抓取时该记录在近 5 次变化中的位次（1 = 最新）」，会随新变盘向前滚动。

create table if not exists public.odds_price_changes (
  sales_day date not null,
  odds_id text not null,
  change_key text not null,
  fixture_id bigint null,
  match_id text null,
  bookmaker_id text null,
  sequence integer null,
  is_opening boolean not null default false,
  handicap numeric null,
  home_odds numeric null,
  away_odds numeric null,
  changed_at_raw text null,
  captured_at timestamptz null,
  raw_sha256 text null,
  source_url text null,
  created_at timestamptz not null default now(),
  primary key (sales_day, odds_id, change_key)
);

create index if not exists odds_price_changes_fixture_idx
  on public.odds_price_changes (fixture_id);

create index if not exists odds_price_changes_sales_day_idx
  on public.odds_price_changes (sales_day);

alter table public.odds_price_changes enable row level security;
