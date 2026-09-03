-- Repo Agent（云端模式）占位表：先保留“能力契约”的落库位置，后续再接入真实执行器/沙箱。
-- 注意：当前版本仅创建表，不会被 Web 自动读写；用于后续迭代时不推倒重来。

create table if not exists public.agent_runtime_settings (
  id text primary key default 'default',
  -- 是否启用 repo agent（默认 false，先保留开关位）
  repo_agent_enabled boolean not null default false,
  -- 云端仓库快照/镜像 ID（可为空；未来可能绑定 commit / zip / mirror）
  repo_snapshot_id text null,
  -- 最近一次变更/执行的追溯字段（占位）
  last_change_id text null,
  last_change_summary text null,
  last_changed_files jsonb null,
  last_tests_run text null,
  last_result text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 单例默认行（便于 upsert）
insert into public.agent_runtime_settings (id)
values ('default')
on conflict (id) do nothing;

-- updated_at 触发器（与其他表一致的写法：若你项目已有统一 trigger，可后续合并）
create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_agent_runtime_settings_updated_at on public.agent_runtime_settings;
create trigger trg_agent_runtime_settings_updated_at
before update on public.agent_runtime_settings
for each row execute function public.set_updated_at();
