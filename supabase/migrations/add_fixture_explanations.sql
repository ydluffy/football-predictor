create table if not exists public.fixture_explanations (
  id bigserial primary key,
  fixture_id bigint not null references public.fixtures (fixture_id) on delete cascade,
  mode text not null default 'brief',
  content text not null,
  source text not null default 'fixture_detail',
  meta jsonb,
  created_at timestamptz not null default now()
);

create index if not exists fixture_explanations_fixture_id_idx on public.fixture_explanations (fixture_id);
create index if not exists fixture_explanations_created_at_idx on public.fixture_explanations (created_at desc);

alter table public.fixture_explanations enable row level security;
