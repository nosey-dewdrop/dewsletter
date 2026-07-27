-- sightstone schema · ortak nosey-dewdrop Supabase'i icin PROJEYE OZEL isimler.
-- Her tablo/fonksiyon "sightstone_" onekiyle: diger projelerle carpisma imkansiz.
-- Supabase SQL editorunde BIR KEZ calistir. Idempotent: tekrar calistirmak guvenli.
--
-- Kapsam bilerek minimal: mail toplama + 100 koltuk + unsubscribe.
-- Ilan/eslesme verisi repo'daki jobs.json'da yasiyor; DB'ye tasinmasi gerekmiyor.

create extension if not exists pgcrypto;

create table if not exists sightstone_subscribers (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  name text,
  level text check (level in ('bs','ms','phd')) default 'bs',
  interests text[] not null default '{}',
  location text,
  remote_ok boolean not null default true,
  cv_text text,                              -- CV'den cikarilan duz metin (deterministik)
  mail_consent boolean not null default false,
  kvkk_accepted_at timestamptz,              -- kayitta zorunlu (RLS zorlar)
  unsubscribe_token uuid not null default gen_random_uuid(),
  unsubscribed_at timestamptz,
  created_at timestamptz not null default now()
);

alter table sightstone_subscribers enable row level security;

-- anon: SADECE onayli kayit ekleyebilir; okuma/guncelleme/silme YOK.
drop policy if exists sightstone_anon_signup on sightstone_subscribers;
create policy sightstone_anon_signup on sightstone_subscribers
  for insert to anon
  with check (mail_consent = true and kvkk_accepted_at is not null);

-- 100 koltuk: doluysa kayit reddedilir; cikan olunca koltuk acilir.
create or replace function sightstone_enforce_cap() returns trigger
language plpgsql security definer as $$
begin
  if (select count(*) from sightstone_subscribers where unsubscribed_at is null) >= 100 then
    raise exception 'no seats left';
  end if;
  return new;
end $$;

drop trigger if exists sightstone_seat_cap on sightstone_subscribers;
create trigger sightstone_seat_cap before insert on sightstone_subscribers
  for each row execute function sightstone_enforce_cap();

-- sitedeki sayac: SADECE iki sayi doner, asla satir donmez.
create or replace function sightstone_seats() returns json
language sql security definer stable as $$
  select json_build_object(
    'capacity', 100,
    'taken', (select count(*) from sightstone_subscribers where unsubscribed_at is null)
  );
$$;
grant execute on function sightstone_seats() to anon;

-- tek tik unsubscribe: maildeki token ile, hesap/sifre gerekmez.
create or replace function sightstone_unsubscribe(token uuid) returns boolean
language plpgsql security definer as $$
declare hit int;
begin
  update sightstone_subscribers
     set unsubscribed_at = now()
   where unsubscribe_token = token and unsubscribed_at is null;
  get diagnostics hit = row_count;
  return hit > 0;
end $$;
grant execute on function sightstone_unsubscribe(uuid) to anon;
