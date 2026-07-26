-- job platform v1 schema (Supabase / Postgres)
-- Run once in Supabase SQL editor. Idempotent where possible.

create extension if not exists pgcrypto;

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  company text not null,
  company_url text,
  position text not null,
  location text,
  remote boolean not null default false,
  salary text,
  link text,                     -- nullable by design: listing may enter without a link
  link_missing boolean not null default false,
  age text,
  deadline date,
  student_ok boolean not null default true,
  first_seen date not null default current_date,
  fetched_at timestamptz not null default now(),
  unique (source, company, position, location)
);

create table if not exists profiles (
  id uuid primary key default gen_random_uuid(),
  auth_user uuid references auth.users(id) on delete cascade,
  email text not null unique,
  name text,
  location text,
  remote_ok boolean not null default true,
  level text check (level in ('bs','ms','phd')) default 'bs',
  interests text[] not null default '{}',   -- selected interest areas
  skills text[] not null default '{}',
  cv_url text,                              -- uploaded CV (storage path)
  cv_text text,                             -- extracted text used to prefill profile
  mail_consent boolean not null default false,
  kvkk_accepted_at timestamptz,             -- explicit consent timestamp, required at signup
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists matches (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references profiles(id) on delete cascade,
  job_id uuid not null references jobs(id) on delete cascade,
  score int not null,
  reasons text[] not null default '{}',     -- human-readable, deterministic
  created_at timestamptz not null default now(),
  unique (profile_id, job_id)
);

create table if not exists sent_mails (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references profiles(id) on delete cascade,
  job_ids uuid[] not null,
  subject text not null,
  sent_at timestamptz not null default now()
);

-- RLS
alter table jobs enable row level security;
alter table profiles enable row level security;
alter table matches enable row level security;
alter table sent_mails enable row level security;

-- jobs are public content (also serves SEO pages)
drop policy if exists jobs_public_read on jobs;
create policy jobs_public_read on jobs for select using (true);

-- a user sees and edits only their own profile
drop policy if exists profiles_own_read on profiles;
create policy profiles_own_read on profiles for select using (auth.uid() = auth_user);
drop policy if exists profiles_own_insert on profiles;
create policy profiles_own_insert on profiles for insert with check (auth.uid() = auth_user);
drop policy if exists profiles_own_update on profiles;
create policy profiles_own_update on profiles for update using (auth.uid() = auth_user);

-- a user sees only their own matches
drop policy if exists matches_own_read on matches;
create policy matches_own_read on matches for select
  using (exists (select 1 from profiles p where p.id = profile_id and p.auth_user = auth.uid()));

-- sent_mails: no client access (service role only)
