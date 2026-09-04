create table if not exists public.sporttery_analysis_runs (
  id bigserial primary key,
  sales_day date not null,
  stage text not null,
  analysis_at timestamptz,
  task_key text null,
  status text null,
  official_on_sale_count int null,
  real_plan_count int not null default 0,
  total_stake numeric not null default 0,
  plan_ids jsonb not null default '[]'::jsonb,
  fixed_shadow_recorded boolean not null default false,
  fixed_shadow_plan_id text null,
  report text null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists sporttery_analysis_runs_identity_idx
  on public.sporttery_analysis_runs (sales_day, stage, analysis_at);
create index if not exists sporttery_analysis_runs_sales_day_idx
  on public.sporttery_analysis_runs (sales_day, analysis_at desc);
create index if not exists sporttery_analysis_runs_task_key_idx
  on public.sporttery_analysis_runs (task_key);

drop trigger if exists sporttery_analysis_runs_set_updated_at on public.sporttery_analysis_runs;
create trigger sporttery_analysis_runs_set_updated_at
before update on public.sporttery_analysis_runs
for each row execute function public.set_updated_at();

alter table public.sporttery_analysis_runs enable row level security;

create table if not exists public.sporttery_review_summaries (
  sales_day date primary key,
  reviewed_at timestamptz null,
  status text null,
  plans int not null default 0,
  hits int not null default 0,
  misses int not null default 0,
  stake numeric not null default 0,
  payout numeric not null default 0,
  net_profit numeric not null default 0,
  roi numeric null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sporttery_review_summaries_reviewed_at_idx
  on public.sporttery_review_summaries (reviewed_at desc);

drop trigger if exists sporttery_review_summaries_set_updated_at on public.sporttery_review_summaries;
create trigger sporttery_review_summaries_set_updated_at
before update on public.sporttery_review_summaries
for each row execute function public.set_updated_at();

alter table public.sporttery_review_summaries enable row level security;

create table if not exists public.sporttery_review_plans (
  id bigserial primary key,
  sales_day date not null,
  reviewed_at timestamptz null,
  plan_id text not null,
  category text not null default '真实方案',
  result text null,
  stake numeric not null default 0,
  payout numeric not null default 0,
  net_profit numeric not null default 0,
  roi numeric null,
  note text null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists sporttery_review_plans_identity_idx
  on public.sporttery_review_plans (sales_day, plan_id, category);
create index if not exists sporttery_review_plans_sales_day_idx
  on public.sporttery_review_plans (sales_day, reviewed_at desc);

drop trigger if exists sporttery_review_plans_set_updated_at on public.sporttery_review_plans;
create trigger sporttery_review_plans_set_updated_at
before update on public.sporttery_review_plans
for each row execute function public.set_updated_at();

alter table public.sporttery_review_plans enable row level security;
