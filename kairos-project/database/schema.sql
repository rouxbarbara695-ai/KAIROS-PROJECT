-- KAIROS — schéma conceptuel initial PostgreSQL.
-- Il sert de contrat de conception avant la création des migrations.

create extension if not exists pgcrypto;

create type listing_status as enum
  ('active', 'sold', 'removed', 'ended', 'unknown');
create type price_kind as enum
  ('asking', 'realized', 'external_estimate', 'kairos_estimate');
create type opportunity_status as enum
  ('watching', 'buy', 'auction', 'purchased', 'in_stock',
   'listed_for_sale', 'awaiting_buyer_payment', 'awaiting_payout',
   'sold', 'abandoned');
create type recommendation as enum
  ('buy', 'watch', 'pass', 'analysis_impossible');
create type confidence_level as enum ('a', 'b', 'c', 'd', 'e');

create table users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  created_at timestamptz not null default now()
);

create table platforms (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table platform_rules (
  id uuid primary key default gen_random_uuid(),
  platform_id uuid not null references platforms(id),
  valid_from timestamptz not null,
  valid_to timestamptz,
  buyer_fee_rate numeric(8,5),
  seller_fee_rate numeric(8,5),
  fixed_fee numeric(14,2),
  currency char(3),
  rules jsonb not null default '{}'::jsonb,
  check (valid_to is null or valid_to > valid_from)
);

create table watch_references (
  id uuid primary key default gen_random_uuid(),
  brand text not null,
  model text,
  reference text not null,
  attributes jsonb not null default '{}'::jsonb,
  unique (brand, reference)
);

create table watches (
  id uuid primary key default gen_random_uuid(),
  reference_id uuid references watch_references(id),
  serial_number text,
  condition_data jsonb not null default '{}'::jsonb,
  completeness_data jsonb not null default '{}'::jsonb,
  identification_confidence numeric(5,2),
  created_at timestamptz not null default now()
);

create table sellers (
  id uuid primary key default gen_random_uuid(),
  platform_id uuid references platforms(id),
  external_id text,
  seller_type text,
  country_code char(2),
  reliability_data jsonb not null default '{}'::jsonb
);

create table listings (
  id uuid primary key default gen_random_uuid(),
  platform_id uuid not null references platforms(id),
  seller_id uuid references sellers(id),
  watch_id uuid references watches(id),
  external_id text,
  canonical_url text not null,
  status listing_status not null default 'unknown',
  first_seen_at timestamptz not null default now(),
  last_success_at timestamptz,
  unique (platform_id, external_id)
);

create table listing_observations (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references listings(id),
  observed_at timestamptz not null,
  status listing_status not null,
  price numeric(14,2),
  currency char(3),
  price_kind price_kind not null default 'asking',
  condition_data jsonb not null default '{}'::jsonb,
  completeness_data jsonb not null default '{}'::jsonb,
  raw_data jsonb not null default '{}'::jsonb,
  fetch_status text not null default 'success',
  error_message text,
  confidence confidence_level not null default 'e',
  unique (listing_id, observed_at)
);

create table opportunities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id),
  listing_id uuid not null references listings(id),
  status opportunity_status not null default 'watching',
  strategy jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table comparables (
  id uuid primary key default gen_random_uuid(),
  reference_id uuid not null references watch_references(id),
  listing_id uuid references listings(id),
  source_name text not null,
  source_external_id text,
  price numeric(14,2) not null,
  currency char(3) not null,
  price_kind price_kind not null,
  occurred_at timestamptz not null,
  confidence confidence_level not null,
  attributes jsonb not null default '{}'::jsonb
);

create table market_valuations (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references opportunities(id),
  calculated_at timestamptz not null default now(),
  low_value numeric(14,2) not null,
  central_value numeric(14,2) not null,
  high_value numeric(14,2) not null,
  currency char(3) not null,
  confidence numeric(5,2) not null,
  trend text,
  rules_version text not null,
  explanation jsonb not null default '{}'::jsonb,
  check (low_value <= central_value and central_value <= high_value)
);

create table valuation_comparables (
  valuation_id uuid not null references market_valuations(id),
  comparable_id uuid not null references comparables(id),
  weight numeric(8,5) not null,
  exclusion_reason text,
  primary key (valuation_id, comparable_id)
);

create table analyses (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references opportunities(id),
  valuation_id uuid not null references market_valuations(id),
  previous_analysis_id uuid references analyses(id),
  trigger_type text not null,
  calculated_at timestamptz not null default now(),
  total_cost numeric(14,2) not null,
  expected_sale_price numeric(14,2) not null,
  max_purchase_price numeric(14,2) not null,
  expected_profit numeric(14,2) not null,
  expected_roi numeric(9,4) not null,
  expected_days_to_sell integer,
  score numeric(5,2),
  recommendation recommendation not null,
  pillars jsonb not null default '{}'::jsonb,
  gates jsonb not null default '{}'::jsonb,
  explanation jsonb not null default '{}'::jsonb,
  rules_version text not null
);

create table alerts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id),
  opportunity_id uuid not null references opportunities(id),
  analysis_id uuid references analyses(id),
  alert_type text not null,
  severity text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  read_at timestamptz
);

create index listing_observations_latest_idx
  on listing_observations (listing_id, observed_at desc);
create index comparables_reference_date_idx
  on comparables (reference_id, occurred_at desc);
create index analyses_opportunity_date_idx
  on analyses (opportunity_id, calculated_at desc);
create index alerts_user_unread_idx
  on alerts (user_id, read_at, created_at desc);
