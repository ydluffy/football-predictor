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
