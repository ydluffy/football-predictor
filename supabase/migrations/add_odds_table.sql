create table if not exists public.odds (
  fixture_id bigint primary key,
  odds_home numeric,
  odds_draw numeric,
  odds_away numeric,
  bookmaker text,
  collected_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists odds_collected_at_idx on public.odds (collected_at);

create or replace function public.odds_set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists odds_set_updated_at on public.odds;
create trigger odds_set_updated_at
before update on public.odds
for each row execute function public.odds_set_updated_at();

alter table public.odds enable row level security;

