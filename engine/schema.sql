-- sightstone schema · ortak nosey-dewdrop Supabase'i icin PROJEYE OZEL isimler.
-- Her tablo/fonksiyon "sightstone_" onekiyle: diger projelerle carpisma imkansiz.
-- Supabase SQL editorunde BIR KEZ calistir. Idempotent: tekrar calistirmak guvenli.
--
-- Kapsam bilerek minimal: mail toplama + 200 koltuk + bekleme listesi + unsubscribe.
-- Ilan/eslesme verisi repo'daki jobs.json'da yasiyor; DB'ye tasinmasi gerekmiyor.
--
-- ACIK KUSUR · GECE PENCERESI (gizlenmiyor, burada yaziyor)
--   Kural: bos koltuk varken kimse bekleme listesinde beklemez. Bos koltuk
--   varsa kayit formu aciktir ve liste bostur; koltuklar doluysa form kapali,
--   liste aciktir. Ikisi ayni anda dolu OLAMAZ.
--   Ama davet dongusu (sightstone_run_invites) GUNDE BIR kosuyor: cagiran
--   engine/send_mail.py'dir, gunluk Actions kosusunun mail adimi. Gece 03:00'te
--   biri unsubscribe ederse koltuk o an bosalir, davet ise ertesi kosuda gider.
--   Arada 24 saati asmayan bir pencere olusur: bos koltuk vardir ve bekleyen de
--   vardir. Bu bilinen bir kusurdur, veri bozulmasi degil -- koltuk kimseye iki
--   kez verilmez, sadece bos bekler. Kapatmak isteyen davet dongusunu sikca
--   kostursun ya da unsubscribe/bounce aninda tetiklesin.

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

-- Mail adresini yanlis yazan koltugu sonsuza kadar tutmasin diye: koltuk ancak
-- ONAYLANINCA kalicidir. Onaylanmamis kayit 48 saat koltugu tutar, sonra birakir.
alter table sightstone_subscribers
  add column if not exists confirmed_at timestamptz;
alter table sightstone_subscribers
  add column if not exists confirm_token uuid not null default gen_random_uuid();

-- Bekleme listesi. Koltuklar doluyken buraya girilir; koltuk bosalinca EN ESKI
-- bekleyene davet gider, 48 saat icinde kabul etmezse davet duser ve siradakine
-- gecer. Davet edilmis ama henuz cevaplanmamis satir bir koltugu REZERVE eder.
create table if not exists sightstone_waitlist (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  mail_consent boolean not null default false,
  kvkk_accepted_at timestamptz,
  invite_token uuid not null default gen_random_uuid(),
  created_at timestamptz not null default now(),   -- sira bu sutuna gore
  invited_at timestamptz,
  invite_expires_at timestamptz,
  accepted_at timestamptz,
  dropped_at timestamptz                           -- davet cevapsiz dustu
);

alter table sightstone_subscribers enable row level security;
alter table sightstone_waitlist enable row level security;

-- anon: SADECE onayli kayit ekleyebilir; okuma/guncelleme/silme YOK.
drop policy if exists sightstone_anon_signup on sightstone_subscribers;
create policy sightstone_anon_signup on sightstone_subscribers
  for insert to anon
  with check (mail_consent = true and kvkk_accepted_at is not null);

drop policy if exists sightstone_anon_waitlist on sightstone_waitlist;
create policy sightstone_anon_waitlist on sightstone_waitlist
  for insert to anon
  with check (mail_consent = true and kvkk_accepted_at is not null);

-- UC TERIMLI SAYIM. Bir koltugu tutan uc sey vardir ve ucu de sayilmalidir:
--   1) onayli abone,
--   2) henuz onaylamamis ama 48 saati dolmamis abone,
--   3) gonderilmis, suresi gecmemis, cevaplanmamis DAVET.
-- Ucuncu terim atlanirsa ayni koltuk iki kisiye davet edilir: davet duruyorken
-- koltuk "bos" gorunur ve dongu bir sonrakine de davet yollar.
create or replace function sightstone_seats_taken() returns int
language sql security definer stable as $$
  select (select count(*) from sightstone_subscribers
           where unsubscribed_at is null
             and (confirmed_at is not null
                  or created_at > now() - interval '48 hours'))
       + (select count(*) from sightstone_waitlist
           where invited_at is not null
             and accepted_at is null
             and dropped_at is null
             and invite_expires_at > now());
$$;

-- 200 koltuk: doluysa kayit reddedilir; cikan olunca koltuk acilir.
-- ILK SATIR advisory kilit. Kilitsiz halde bu trigger yaristi: 99/100 doluyken
-- 20 escesamanli insert 119 abone birakiyordu, cunku hepsi kendi anlik
-- goruntusunde sayimi 99 goruyordu. pg_advisory_xact_lock sayimi ve insert'i
-- tek bir seri hatta diziyor; kilit transaction bitince kendiliginden birakilir.
create or replace function sightstone_enforce_cap() returns trigger
language plpgsql security definer as $$
begin
  perform pg_advisory_xact_lock(hashtext('sightstone_seats'));
  if sightstone_seats_taken() >= 200 then
    raise exception 'no seats left';
  end if;
  return new;
end $$;

drop trigger if exists sightstone_seat_cap on sightstone_subscribers;
create trigger sightstone_seat_cap before insert on sightstone_subscribers
  for each row execute function sightstone_enforce_cap();

-- D8: bos koltuk varken kimse bekleyemez. Bos koltuk varken gelen bekleme
-- kaydi reddedilir -- o kisinin yeri form, liste degil.
create or replace function sightstone_waitlist_guard() returns trigger
language plpgsql security definer as $$
begin
  perform pg_advisory_xact_lock(hashtext('sightstone_seats'));
  if sightstone_seats_taken() < (sightstone_seats() ->> 'capacity')::int then
    raise exception 'seats available, use the signup form';
  end if;
  return new;
end $$;

drop trigger if exists sightstone_waitlist_gate on sightstone_waitlist;
create trigger sightstone_waitlist_gate before insert on sightstone_waitlist
  for each row execute function sightstone_waitlist_guard();

-- sitedeki sayac: SADECE iki sayi doner, asla satir donmez.
create or replace function sightstone_seats() returns json
language sql security definer stable as $$
  select json_build_object(
    'capacity', 200,
    'taken', sightstone_seats_taken()
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

-- maildeki onay linki. Onaylanana kadar koltuk 48 saatlik kiradadir.
create or replace function sightstone_confirm(token uuid) returns boolean
language plpgsql security definer as $$
declare hit int;
begin
  update sightstone_subscribers
     set confirmed_at = now()
   where confirm_token = token
     and unsubscribed_at is null
     and confirmed_at is null
     and created_at > now() - interval '48 hours';
  get diagnostics hit = row_count;
  return hit > 0;
end $$;
grant execute on function sightstone_confirm(uuid) to anon;

-- SERT bounce: adres kalici olarak olu. Koltugu hemen birakir.
-- anon'a VERILMEZ: yoksa herkes baskasinin adresini yazip onu attirir.
create or replace function sightstone_mark_bounce(addr text) returns boolean
language plpgsql security definer as $$
declare hit int;
begin
  update sightstone_subscribers
     set unsubscribed_at = now()
   where lower(email) = lower(addr) and unsubscribed_at is null;
  get diagnostics hit = row_count;
  return hit > 0;
end $$;

-- PostgreSQL yeni fonksiyona EXECUTE'u varsayilan olarak PUBLIC'e verir.
-- "anon'a grant vermedim" YETMEZ: grant satiri olmadan da anon bu fonksiyonlari
-- cagirabilirdi ve ikisi de security definer. Yani anon herhangi bir abonenin
-- adresini yazip onu attirabilir, ya da davet dongusunu istedigi an kosturup
-- koltuk dagittirabilirdi. Bu yuzden PUBLIC'ten acikca geri aliniyor.
-- (Asagidaki sightstone_run_invites da ayni sebeple revoke ediliyor.)
revoke execute on function sightstone_mark_bounce(text) from public;
revoke execute on function sightstone_seats_taken() from public;

-- davet kabulu: bekleyen koltugunu alir ve dogrudan ONAYLI abone olur.
create or replace function sightstone_accept_invite(token uuid) returns boolean
language plpgsql security definer as $$
declare w sightstone_waitlist;
begin
  perform pg_advisory_xact_lock(hashtext('sightstone_seats'));
  select * into w from sightstone_waitlist
   where invite_token = token
     and invited_at is not null
     and accepted_at is null
     and dropped_at is null
     and invite_expires_at > now();
  if not found then
    return false;
  end if;
  -- Once accepted_at yazilir. Satir "cevap bekleyen davet" olmaktan ayni anda
  -- cikar ve "onayli abone" olarak geri sayilir; koltuk bir an bile iki kez
  -- sayilmaz, bu yuzden asagidaki insert kendi rezervasyonuna carpmaz.
  update sightstone_waitlist set accepted_at = now() where id = w.id;
  insert into sightstone_subscribers (email, mail_consent, kvkk_accepted_at, confirmed_at)
       values (w.email, true, coalesce(w.kvkk_accepted_at, now()), now());
  return true;
end $$;
grant execute on function sightstone_accept_invite(uuid) to anon;

-- GUNLUK DAVET DONGUSU. Once cevapsiz kalmis davetleri dusurur (koltuklarini
-- geri verir), sonra bos koltuk sayisi kadar EN ESKI bekleyene davet yollar.
-- Kac davet gonderdigini doner. Yukaridaki "gece penceresi" notu bu fonksiyonun
-- gunde bir kosmasindan dogar.
--
-- DAILY_LIMIT NEDEN VAR (S9b). Bu damga bir SOZ: invited_at yazildigi an o
-- kisiye "sira sende, 48 saatin var" denmis olur, ve o soz bir MAILLE tutulur.
-- Damgayi mail kapasitesinden bagimsiz atmak, tutulamayacak soz vermektir:
-- 200 kisilik listede 199 koltuk bosalirsa parametresiz surum 199 satiri tek
-- seferde damgalar, saglayici gunde 90 maile izin verir, geri kalan 109 kisi
-- HIC MAIL ALMADAN 48 saat sonra dropped_at olur. Sirasi gelmisti, haberi
-- olmadi. daily_limit o yuzden buradadir: damga sayisi, bugun atilabilecek
-- mail sayisini asamaz. Cagiran (send_mail.py) buraya kendi gunluk kota
-- bakiyesini -- remaining_today() -- gecirir.
--
-- least(free, daily_limit): iki tavandan hangisi alcaksa o baglar. coalesce
-- ile null 0'a duser, cunku least(5, null) = 5 -- null bir "sinir yok"
-- olarak okunsaydi parametre hic konmamis gibi davranirdi.
--
-- Parametresiz eski surum bilerek DUSURULUYOR. create or replace yeni imzayi
-- yaratir ama eskisini yerinde birakir: schema.sql iki kez kosturulunca
-- sightstone_run_invites() hala orada durur ve delik acik kalir.
drop function if exists sightstone_run_invites();
create or replace function sightstone_run_invites(daily_limit int) returns int
language plpgsql security definer as $$
declare
  free int;
  sent int := 0;
  w record;
begin
  perform pg_advisory_xact_lock(hashtext('sightstone_seats'));

  update sightstone_waitlist
     set dropped_at = now()
   where invited_at is not null
     and accepted_at is null
     and dropped_at is null
     and invite_expires_at <= now();

  free := (sightstone_seats() ->> 'capacity')::int - sightstone_seats_taken();

  for w in
    select id from sightstone_waitlist
     where invited_at is null and accepted_at is null and dropped_at is null
     order by created_at, id
     limit greatest(least(free, coalesce(daily_limit, 0)), 0)
  loop
    update sightstone_waitlist
       set invited_at = now(),
           invite_expires_at = now() + interval '48 hours'
     where id = w.id;
    sent := sent + 1;
  end loop;

  return sent;
end $$;
revoke execute on function sightstone_run_invites(int) from public;

-- ---------------------------------------------------------------------------
-- D2 BACKFILL -- one address, once, by name.
--
-- send_mail.fetch_subscribers now drops every row whose confirmed_at is null,
-- because mailing an address that never clicked confirm is the KVKK/GDPR
-- violation confirmed_at exists to prevent. The founding subscriber signed up
-- on 2026-07-27, BEFORE the confirm flow existed (S6 added the column), so her
-- row has no confirmed_at and would go silent the moment the filter shipped.
--
-- She is named here on purpose. A blanket
--   update sightstone_subscribers set confirmed_at = now() where confirmed_at is null
-- would be the exact violation this change is closing: it would manufacture
-- consent for anyone who ever typed their address in. One address, spelled out,
-- auditable in the diff. Everyone else confirms by clicking.
update sightstone_subscribers
   set confirmed_at = coalesce(confirmed_at, created_at, now())
 where email = 'teenagemutantdamlaturtle@gmail.com';

-- ---------------------------------------------------------------------------
-- A3 -- drop the cv_text column. Nothing has ever written to it.
--
-- The site's promise is that a CV is read in the browser and never uploaded;
-- cv.html does the whole critique client-side and the engine has no code that
-- sends CV text anywhere (measure.py's D5 scan finds zero writers). But the
-- column sat here READY to store it, which makes the promise a matter of
-- nobody having written the insert yet rather than the schema refusing it.
-- Removing it makes D5 structural instead of behavioural.
alter table sightstone_subscribers drop column if exists cv_text;

-- ---------------------------------------------------------------------------
-- KUYRUK TAVANI. Ölçüldü (1 Eyl, gerçek küme): koltuklar dolduğu anda anon
-- kuyruğa SINIRSIZ satır yazabiliyordu. 20.000 satır 3.872 kB yer kapladı,
-- satır başı ~198 bayt; Supabase'in bedava 500 MB'ı ~2,65 milyon satırda dolar.
-- Bir bot için erişilebilir bir sayı, ve dolduğunda proje durur.
--
-- Tavan koltuk sayısının on katı: gerçek bir kuyruk asla o kadar uzun olmaz
-- (200 koltuk, 48 saatte devreden davetler), ama meşru bir yığılmayı da
-- kesmez. Koltuk tavanı gibi advisory kilitle sayılıyor, yoksa eşzamanlı
-- insert'ler kendi anlık görüntülerinde tavanın altını görür ve hep birlikte
-- geçerler -- koltuk trigger'ında ölçülen 119/100 hatası.
create or replace function sightstone_waitlist_cap() returns trigger
language plpgsql security definer as $$
begin
  perform pg_advisory_xact_lock(hashtext('sightstone_waitlist_len'));
  if (select count(*) from sightstone_waitlist
       where accepted_at is null and dropped_at is null) >= 2000 then
    raise exception 'waitlist is full';
  end if;
  return new;
end $$;

drop trigger if exists sightstone_waitlist_len on sightstone_waitlist;
create trigger sightstone_waitlist_len before insert on sightstone_waitlist
  for each row execute function sightstone_waitlist_cap();
