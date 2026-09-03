-- 为“体彩赛程 / 体彩预测”落库做扩展字段（不破坏现有表结构）
-- 说明：
-- 1) 本项目已有 fixtures / fixture_predictions 等表；当前前端已能直接读取本地体彩产物展示。
-- 2) 但为了支持“历史查询 / 复盘 / 回测可追溯”，需要把关键字段同步到 Supabase。
-- 3) 这些字段均为可空，未同步时不会影响旧逻辑。

-- fixtures：补充数据来源与体彩销售日信息（便于按销售日查询）
alter table public.fixtures add column if not exists data_source text;
alter table public.fixtures add column if not exists sporttery_sales_day date;
alter table public.fixtures add column if not exists sporttery_match_number text;

create index if not exists fixtures_sporttery_sales_day_idx on public.fixtures (sporttery_sales_day);

-- fixture_predictions：补充体彩让球（用于离线/历史复现让球展示），以及预测来源标记
alter table public.fixture_predictions add column if not exists sporttery_handicap numeric;
alter table public.fixture_predictions add column if not exists prediction_source text;

create index if not exists fixture_predictions_prediction_source_idx on public.fixture_predictions (prediction_source);
