-- BYOK（用户自带 Key）模型配置：用于总控助手 /api/chat 调用大模型
-- 注意：当前项目未接入 Supabase Auth 的用户体系，因此先按“项目级配置”落库。
-- 后续若接入 Auth，可新增 owner_user_id 并按用户隔离。

-- gen_random_uuid 依赖 pgcrypto；Supabase 默认已启用，若失败可在 SQL Editor 手动启用：
-- create extension if not exists pgcrypto;

create table if not exists public.llm_provider_configs (
  id uuid primary key default gen_random_uuid(),
  label text not null,
  provider text not null default 'openai_compatible', -- openai_compatible / openrouter 等（先按 openai_compatible 落地）
  base_url text not null, -- 例如 https://api.openai.com/v1 或某国内模型网关的兼容地址（包含 /v1）
  model text not null,
  encrypted_api_key text not null, -- 服务端加密后的 key（前端永不回显明文）
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists llm_provider_configs_created_at_idx on public.llm_provider_configs (created_at);

-- updated_at trigger（复用已有 set_updated_at）
drop trigger if exists llm_provider_configs_set_updated_at on public.llm_provider_configs;
create trigger llm_provider_configs_set_updated_at
before update on public.llm_provider_configs
for each row execute function public.set_updated_at();

alter table public.llm_provider_configs enable row level security;

-- 当前启用的模型配置（单行表）
create table if not exists public.llm_runtime_settings (
  id text primary key default 'default',
  active_config_id uuid null references public.llm_provider_configs(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists llm_runtime_settings_set_updated_at on public.llm_runtime_settings;
create trigger llm_runtime_settings_set_updated_at
before update on public.llm_runtime_settings
for each row execute function public.set_updated_at();

alter table public.llm_runtime_settings enable row level security;
