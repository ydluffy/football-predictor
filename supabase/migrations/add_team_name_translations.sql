create table if not exists public.team_name_translations (
  name_norm text primary key,
  name_original text,
  name_zh text not null,
  provider text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists team_name_translations_name_zh_idx on public.team_name_translations (name_zh);

create or replace function public.team_name_translations_set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists team_name_translations_set_updated_at on public.team_name_translations;
create trigger team_name_translations_set_updated_at
before update on public.team_name_translations
for each row execute function public.team_name_translations_set_updated_at();

alter table public.team_name_translations enable row level security;

