-- Filament Tracker: multi-user schema for Supabase Postgres.
--
-- Every row belongs to a Supabase Auth user. Row-level security (RLS)
-- makes sure a user can only ever read or write their own rows; the
-- Flask app runs each request as the `authenticated` role with the
-- user's id in `request.jwt.claims`, so `auth.uid()` resolves to them.
--
-- Run this once in the Supabase SQL editor (or `supabase db push`).

-- ------------------------------------------------------------ settings
create table if not exists public.user_settings (
    user_id          uuid primary key default auth.uid()
                     references auth.users (id) on delete cascade,
    slot_count       int  not null default 1 check (slot_count between 1 and 4),
    device_id        text not null default '',
    bambu_email      text not null default '',
    bambu_region     text not null default 'global'
                     check (bambu_region in ('global', 'china')),
    bambu_token_enc  text,               -- Fernet-encrypted by the app
    last_sync        timestamptz,
    created_at       timestamptz not null default now()
);

-- ------------------------------------------------------------ spools
create table if not exists public.spools (
    id          bigint generated always as identity primary key,
    user_id     uuid not null default auth.uid()
                references auth.users (id) on delete cascade,
    slot        int  not null default 1 check (slot between 1 and 4),
    brand       text not null default '',
    material    text not null default 'PLA',
    color       text not null default '',
    initial_g   numeric(10, 2) not null check (initial_g > 0),
    note        text not null default '',
    started_at  timestamptz not null default now(),
    ended_at    timestamptz,
    active      boolean not null default true,
    -- lets child tables reference (id, user_id) so a row can never point
    -- at another user's spool
    unique (id, user_id)
);
-- at most one active spool per slot per user
create unique index if not exists spools_one_active_per_slot
    on public.spools (user_id, slot) where active;

-- ------------------------------------------------------------ prints
create table if not exists public.prints (
    id          bigint generated always as identity primary key,
    user_id     uuid not null default auth.uid()
                references auth.users (id) on delete cascade,
    task_key    text,                    -- Bambu task id (+ slot suffix)
    title       text not null default 'Untitled',
    device_id   text,
    status      int,
    start_time  timestamptz,
    end_time    timestamptz,
    weight      numeric(10, 2) not null default 0,
    slot        int not null default 1,
    spool_id    bigint,
    counted     boolean not null default true,
    source      text not null default 'cloud' check (source in ('cloud', 'manual')),
    unique (user_id, task_key),
    foreign key (spool_id, user_id)
        references public.spools (id, user_id) on delete set null (spool_id)
);
create index if not exists prints_user_spool on public.prints (user_id, spool_id);
create index if not exists prints_user_start on public.prints (user_id, start_time desc);

-- ------------------------------------------------------------ adjustments
create table if not exists public.adjustments (
    id          bigint generated always as identity primary key,
    user_id     uuid not null default auth.uid()
                references auth.users (id) on delete cascade,
    spool_id    bigint not null,
    grams       numeric(10, 2) not null,
    note        text not null default '',
    created_at  timestamptz not null default now(),
    foreign key (spool_id, user_id)
        references public.spools (id, user_id) on delete cascade
);

-- ------------------------------------------------------------ RLS
alter table public.user_settings enable row level security;
alter table public.spools        enable row level security;
alter table public.prints        enable row level security;
alter table public.adjustments   enable row level security;

do $$
declare t text;
begin
  foreach t in array array['user_settings', 'spools', 'prints', 'adjustments'] loop
    execute format('drop policy if exists "own rows" on public.%I', t);
    execute format(
      'create policy "own rows" on public.%I for all to authenticated '
      'using (user_id = (select auth.uid())) '
      'with check (user_id = (select auth.uid()))', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end $$;

-- ------------------------------------------------------------ stats view
-- Per-spool usage, computed in the database. security_invoker makes the
-- view run with the caller's permissions, so RLS still applies.
create or replace view public.spool_stats
with (security_invoker = true) as
select
    s.*,
    round(coalesce(p.used, 0) + coalesce(a.adj, 0), 2)               as used_g,
    round(s.initial_g - coalesce(p.used, 0) - coalesce(a.adj, 0), 2) as remaining_g,
    coalesce(p.n, 0)                                                 as print_count
from public.spools s
left join (
    select spool_id, sum(weight) as used, count(*) as n
    from public.prints where counted group by spool_id
) p on p.spool_id = s.id
left join (
    select spool_id, sum(grams) as adj
    from public.adjustments group by spool_id
) a on a.spool_id = s.id;

revoke all on public.spool_stats from anon;
grant select on public.spool_stats to authenticated;

-- ------------------------------------------------------------ functions
-- All functions are SECURITY INVOKER (the default): they run as the
-- calling user, so the RLS policies above still apply inside them.

-- Import print jobs fetched from Bambu Cloud. New jobs are charged to the
-- slot's active spool only if they started after that spool was loaded;
-- older history comes in unassigned. Jobs already imported only get their
-- status and end time refreshed, so manual fixes (spool, counted) survive.
create or replace function public.import_prints(p_rows jsonb)
returns table (inserted int, updated int)
language plpgsql
set search_path = public
as $$
declare
    v_ins int;
    v_upd int;
begin
    with src as (
        select *
        from jsonb_to_recordset(p_rows) as r(
            task_key text, title text, device_id text, status int,
            start_time timestamptz, end_time timestamptz,
            weight numeric, slot int)
    ), up as (
        insert into prints (task_key, title, device_id, status, start_time,
                            end_time, weight, slot, spool_id, source)
        select s.task_key, coalesce(nullif(s.title, ''), 'Untitled'), s.device_id,
               s.status, s.start_time, s.end_time, coalesce(s.weight, 0),
               coalesce(s.slot, 1),
               (select sp.id from spools sp
                 where sp.active and sp.slot = coalesce(s.slot, 1)
                   and s.start_time is not null
                   and s.start_time >= sp.started_at
                 limit 1),
               'cloud'
        from src s
        on conflict (user_id, task_key) do update
            set status = excluded.status, end_time = excluded.end_time
            where prints.source = 'cloud'
        returning (xmax = 0) as is_insert
    )
    select count(*) filter (where is_insert),
           count(*) filter (where not is_insert)
      into v_ins, v_upd
      from up;

    update user_settings set last_sync = now() where user_id = auth.uid();
    return query select v_ins, v_upd;
end $$;

-- Archive the slot's current spool (if any) and load a new one.
create or replace function public.change_spool(
    p_slot int, p_initial_g numeric, p_material text,
    p_color text, p_brand text, p_note text)
returns bigint
language plpgsql
set search_path = public
as $$
declare
    v_id bigint;
begin
    update spools set active = false, ended_at = now()
     where slot = p_slot and active;
    insert into spools (slot, initial_g, material, color, brand, note)
    values (p_slot, p_initial_g, coalesce(p_material, 'PLA'),
            coalesce(p_color, ''), coalesce(p_brand, ''), coalesce(p_note, ''))
    returning id into v_id;
    return v_id;
end $$;

-- Correct a spool after weighing it: records the difference between the
-- tracked and measured remaining grams as an adjustment.
create or replace function public.set_remaining(
    p_spool_id bigint, p_measured_g numeric, p_note text default 'manual correction')
returns numeric
language plpgsql
set search_path = public
as $$
declare
    v_diff numeric;
begin
    select round(remaining_g - p_measured_g, 2) into v_diff
      from spool_stats where id = p_spool_id;
    if v_diff is null then
        raise exception 'spool % not found', p_spool_id using errcode = 'P0002';
    end if;
    if v_diff <> 0 then
        insert into adjustments (spool_id, grams, note)
        values (p_spool_id, v_diff, coalesce(nullif(p_note, ''), 'manual correction'));
    end if;
    return v_diff;
end $$;

revoke all on function public.import_prints(jsonb) from public, anon;
revoke all on function public.change_spool(int, numeric, text, text, text, text) from public, anon;
revoke all on function public.set_remaining(bigint, numeric, text) from public, anon;
grant execute on function public.import_prints(jsonb) to authenticated;
grant execute on function public.change_spool(int, numeric, text, text, text, text) to authenticated;
grant execute on function public.set_remaining(bigint, numeric, text) to authenticated;
