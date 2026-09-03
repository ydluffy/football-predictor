-- 自动化总控：override / registry / controller state 入库（用于 Web 展示与多端协作）
-- 设计原则：
-- 1) 先入库“原始 JSON + 关键索引字段”，避免过早做过度规范化导致反复迁移。
-- 2) 后续若要做更细的 analytics，可以再从 payload 派生 staging/fact 表。

-- 统一 updated_at trigger（如果已存在则复用）
create or replace function public.set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- 每日调度覆盖（用户临时调整采样点/分组）
create table if not exists public.automation_daily_overrides (
  sales_day date primary key,
  requested_at timestamptz,
  requested_by text,
  official_confirmed_count int,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists automation_daily_overrides_set_updated_at on public.automation_daily_overrides;
create trigger automation_daily_overrides_set_updated_at
before update on public.automation_daily_overrides
for each row execute function public.set_updated_at();

create index if not exists automation_daily_overrides_requested_at_idx on public.automation_daily_overrides (requested_at);

alter table public.automation_daily_overrides enable row level security;

-- 每日任务注册表（控制器执行状态：scheduled/completed/failed 等）
create table if not exists public.automation_task_registries (
  sales_day date primary key,
  registry_updated_at timestamptz,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists automation_task_registries_set_updated_at on public.automation_task_registries;
create trigger automation_task_registries_set_updated_at
before update on public.automation_task_registries
for each row execute function public.set_updated_at();

create index if not exists automation_task_registries_registry_updated_at_idx on public.automation_task_registries (registry_updated_at);

alter table public.automation_task_registries enable row level security;

-- 控制器当前状态（单行表：谁在跑、下次唤醒、最近完成阶段等）
create table if not exists public.automation_controller_state (
  id text primary key default 'default',
  controller_month text,
  execution_environment text,
  status text,
  last_rescheduled_at timestamptz,
  last_reschedule_target timestamptz,
  next_required_at timestamptz,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists automation_controller_state_set_updated_at on public.automation_controller_state;
create trigger automation_controller_state_set_updated_at
before update on public.automation_controller_state
for each row execute function public.set_updated_at();

alter table public.automation_controller_state enable row level security;
