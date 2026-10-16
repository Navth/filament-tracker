-- Database tests for supabase/migrations/20261017000000_multi_user.sql.
-- Run against a scratch Postgres that has tests/supabase_stub.sql and the
-- migration applied. Any failed check raises an exception (psql exits 3
-- with ON_ERROR_STOP=1).

\set ON_ERROR_STOP 1
\set alice '11111111-1111-1111-1111-111111111111'
\set bob   '22222222-2222-2222-2222-222222222222'

insert into auth.users (id, email) values
  (:'alice', 'alice@example.com'), (:'bob', 'bob@example.com')
on conflict do nothing;

create or replace function pg_temp.assert(cond boolean, msg text) returns void
language plpgsql as $$ begin
  if cond is distinct from true then raise exception 'FAILED: %', msg; end if;
  raise notice 'ok - %', msg;
end $$;

create or replace function pg_temp.act_as(uid uuid) returns void
language plpgsql as $$ begin
  perform set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, false);
end $$;

-- ================================================================ alice
set role authenticated;
select pg_temp.act_as(:'alice');

insert into user_settings default values;
select pg_temp.assert((select count(*) from user_settings) = 1, 'alice gets a settings row via default auth.uid()');

-- load a PLA spool in slot 1, backdated so older prints can match
select change_spool(1, 1000, 'PLA', '#22aa55', 'Bambu', '') as alice_spool \gset
update spools set started_at = '2026-01-01T00:00:00Z' where id = :alice_spool;

select pg_temp.assert(
  (select count(*) from spools where active and slot = 1) = 1,
  'change_spool loads one active spool');

-- import: one print after load, one before load, one in slot 2 (no spool)
select * from import_prints('[
  {"task_key":"t1","title":"Benchy","status":2,"start_time":"2026-02-01T10:00:00Z","end_time":"2026-02-01T11:00:00Z","weight":12.5,"slot":1},
  {"task_key":"t0","title":"Old print","status":2,"start_time":"2025-12-01T10:00:00Z","end_time":"2025-12-01T11:00:00Z","weight":40,"slot":1},
  {"task_key":"t2","title":"Slot two","status":2,"start_time":"2026-02-02T10:00:00Z","end_time":"2026-02-02T11:00:00Z","weight":5,"slot":2}
]'::jsonb) \gset imp_

select pg_temp.assert(:imp_inserted = 3 and :imp_updated = 0, 'first import inserts 3');
select pg_temp.assert(
  (select spool_id from prints where task_key = 't1') = :alice_spool,
  'print after spool load is charged to the active spool');
select pg_temp.assert(
  (select spool_id from prints where task_key = 't0') is null,
  'print before spool load stays unassigned');
select pg_temp.assert(
  (select spool_id from prints where task_key = 't2') is null,
  'print in a slot with no spool stays unassigned');
select pg_temp.assert(
  (select last_sync is not null from user_settings), 'import sets last_sync');

-- a manual fix must survive re-import; status/end_time refresh
update prints set counted = false where task_key = 't0';
select * from import_prints('[
  {"task_key":"t0","title":"Old print","status":3,"start_time":"2025-12-01T10:00:00Z","end_time":"2025-12-01T12:00:00Z","weight":40,"slot":1}
]'::jsonb) \gset imp_
select pg_temp.assert(:imp_inserted = 0 and :imp_updated = 1, 're-import updates instead of inserting');
select pg_temp.assert(
  (select status = 3 and not counted from prints where task_key = 't0'),
  're-import refreshes status but keeps counted=false');

-- stats: 1000 - 12.5 = 987.5
select pg_temp.assert(
  (select remaining_g = 987.5 and used_g = 12.5 and print_count = 1 from spool_stats where id = :alice_spool),
  'spool_stats computes used and remaining grams');

-- weigh the spool: 950 g actually left -> adjustment of 37.5
select set_remaining(:alice_spool, 950) as diff \gset
select pg_temp.assert(:diff = 37.5, 'set_remaining records the difference');
select pg_temp.assert(
  (select remaining_g from spool_stats where id = :alice_spool) = 950,
  'remaining matches the weighed value after correction');

-- changing the spool archives the old one
select change_spool(1, 750, 'PETG', '#000000', '', 'new') as alice_spool2 \gset
select pg_temp.assert(
  (select not active and ended_at is not null from spools where id = :alice_spool),
  'change_spool archives the previous spool');
select pg_temp.assert(
  (select count(*) from spools where active and slot = 1) = 1,
  'still exactly one active spool in slot 1');

-- ================================================================ bob
select pg_temp.act_as(:'bob');

select pg_temp.assert((select count(*) from spools) = 0, 'bob cannot see alice''s spools');
select pg_temp.assert((select count(*) from prints) = 0, 'bob cannot see alice''s prints');
select pg_temp.assert((select count(*) from spool_stats) = 0, 'spool_stats view respects RLS');
select pg_temp.assert((select count(*) from user_settings) = 0, 'bob cannot see alice''s settings');

-- bob updating/deleting alice's rows affects nothing
update spools set initial_g = 1 where id = :alice_spool2;
delete from prints;
select pg_temp.act_as(:'alice');
select pg_temp.assert(
  (select initial_g from spools where id = :alice_spool2) = 750,
  'bob''s update did not touch alice''s spool');
select pg_temp.assert((select count(*) from prints) = 3, 'bob''s delete did not touch alice''s prints');
select pg_temp.act_as(:'bob');

-- expose alice's spool id to the DO blocks below
select set_config('test.alice_spool', :'alice_spool2', false);

-- bob cannot correct alice's spool through the function
do $$ begin
  perform set_remaining(current_setting('test.alice_spool')::bigint, 1);
  raise exception 'FAILED: bob corrected alice''s spool';
exception when sqlstate 'P0002' then
  raise notice 'ok - set_remaining cannot see another user''s spool';
end $$;

-- bob cannot insert a row owned by alice
do $$ begin
  insert into spools (user_id, slot, initial_g) values ('11111111-1111-1111-1111-111111111111', 1, 500);
  raise exception 'FAILED: bob inserted a row for alice';
exception when insufficient_privilege then
  raise notice 'ok - RLS blocks inserting rows for another user';
end $$;

-- bob cannot point his print at alice's spool (composite FK)
do $$ begin
  insert into prints (title, weight, spool_id, source)
  values ('sneaky', 1, current_setting('test.alice_spool')::bigint, 'manual');
  raise exception 'FAILED: bob linked a print to alice''s spool';
exception when foreign_key_violation then
  raise notice 'ok - prints cannot reference another user''s spool';
end $$;

-- ================================================================ anon
reset role;
set role anon;
do $$ begin
  perform count(*) from public.spools;
  raise exception 'FAILED: anon can read spools';
exception when insufficient_privilege then
  raise notice 'ok - anon has no access to tables';
end $$;
do $$ begin
  perform import_prints('[]'::jsonb);
  raise exception 'FAILED: anon can call import_prints';
exception when insufficient_privilege then
  raise notice 'ok - anon cannot call functions';
end $$;
reset role;

\echo ALL SQL TESTS PASSED
