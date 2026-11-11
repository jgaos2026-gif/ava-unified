-- Jay's Graphic Arts — Brick 1 pipeline tables (Supabase / Postgres)
-- Apply in the Supabase SQL editor. Uses the brick1_ prefix so these
-- never collide with the stitch_* tables in the same project.
-- Row Level Security is enabled; add policies for your access pattern
-- (server-side service-role use is the intended pattern for this app).

create table if not exists brick1_customers (
  id bigint generated always as identity primary key,
  name text not null,
  email text,
  phone text,
  created_at timestamptz not null default now()
);

create table if not exists brick1_jobs (
  id bigint generated always as identity primary key,
  customer text not null,
  package text not null,
  brief text not null,
  state text not null default 'INTAKE',
  price_cents integer not null default 0,
  deposit_cleared boolean not null default false,
  final_paid boolean not null default false,
  client_approved boolean not null default false,
  revisions_used integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists brick1_proofs (
  id bigint generated always as identity primary key,
  job_id bigint references brick1_jobs(id),
  artifact_ref text not null,
  watermarked boolean not null default true,
  client_approved boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists brick1_invoices (
  id bigint generated always as identity primary key,
  job_id bigint references brick1_jobs(id),
  customer text not null,
  package text not null,
  price_cents integer not null,
  deposit_cents integer not null,
  balance_cents integer not null,
  receipt_sha256 text not null,
  created_at timestamptz not null default now()
);

create table if not exists brick1_error_samples (
  id bigint generated always as identity primary key,
  job_ref text,
  error_found boolean not null,
  created_at timestamptz not null default now()
);

alter table brick1_customers enable row level security;
alter table brick1_jobs enable row level security;
alter table brick1_proofs enable row level security;
alter table brick1_invoices enable row level security;
alter table brick1_error_samples enable row level security;
