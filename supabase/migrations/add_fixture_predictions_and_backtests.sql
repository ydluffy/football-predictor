create table if not exists public.fixture_predictions (
  fixture_id bigint primary key,
  model_version text not null default 'poisson_v1',
  as_of_date date,
  generated_at timestamptz not null default now(),

  p_home numeric,
  p_draw numeric,
  p_away numeric,
  confidence numeric,
  lambda_home numeric,
  lambda_away numeric,

  p_over_2_5 numeric,
  p_under_2_5 numeric,
  p_btts_yes numeric,
  p_btts_no numeric,

  odds_home numeric,
  odds_draw numeric,
  odds_away numeric,
  bookmaker text,

  ev_home numeric,
  ev_draw numeric,
  ev_away numeric,
  kelly_home numeric,
  kelly_draw numeric,
  kelly_away numeric,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists fixture_predictions_generated_at_idx on public.fixture_predictions (generated_at);
create index if not exists fixture_predictions_as_of_date_idx on public.fixture_predictions (as_of_date);

create or replace function public.fixture_predictions_set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists fixture_predictions_set_updated_at on public.fixture_predictions;
create trigger fixture_predictions_set_updated_at
before update on public.fixture_predictions
for each row execute function public.fixture_predictions_set_updated_at();

alter table public.fixture_predictions enable row level security;

create table if not exists public.backtest_runs (
  id bigserial primary key,
  model_version text not null,
  date_from date not null,
  date_to date not null,
  computed_at timestamptz not null default now(),
  n int not null,
  accuracy numeric,
  logloss numeric,
  brier numeric,
  meta jsonb
);

create index if not exists backtest_runs_computed_at_idx on public.backtest_runs (computed_at);
alter table public.backtest_runs enable row level security;

