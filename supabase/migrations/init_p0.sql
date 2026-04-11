create table if not exists public.fixtures (
  fixture_id bigint primary key,
  competition_code text,
  competition_name text,
  season int,
  matchday int,
  utc_date timestamptz,
  status text,
  home_team_id bigint,
  home_team_name text,
  away_team_id bigint,
  away_team_name text,
  home_score int,
  away_score int,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists fixtures_utc_date_idx on public.fixtures (utc_date);
create index if not exists fixtures_competition_code_idx on public.fixtures (competition_code);

create or replace function public.set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists fixtures_set_updated_at on public.fixtures;
create trigger fixtures_set_updated_at
before update on public.fixtures
for each row execute function public.set_updated_at();

alter table public.fixtures enable row level security;
