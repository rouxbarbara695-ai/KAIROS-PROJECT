-- KAIROS V2 — contrat de schéma PostgreSQL réconcilié.
-- Les migrations d'implémentation doivent produire ce schéma et ses seeds.

create extension if not exists pgcrypto;
create extension if not exists btree_gist;

create type listing_status as enum
  ('active', 'sold', 'removed', 'ended', 'unknown');
create type price_kind as enum
  ('asking', 'offer', 'accepted_offer', 'current_bid', 'hammer',
   'realized', 'external_estimate', 'kairos_estimate');
create type opportunity_source_mode as enum
  ('manual', 'url', 'assisted_import', 'connector');
create type opportunity_status as enum
  ('watching', 'buy', 'auction', 'purchased', 'in_stock',
   'listed_for_sale', 'awaiting_buyer_payment', 'awaiting_payout',
   'sold', 'abandoned');
create type recommendation as enum
  ('buy', 'watch', 'pass', 'analysis_impossible');
create type source_reliability_level as enum ('a', 'b', 'c', 'd', 'e');
create type reference_confirmation_status as enum
  ('unconfirmed', 'suggested', 'confirmed', 'corrected', 'unknown');
create type gate_status as enum
  ('passed', 'passed_with_warning', 'failed', 'not_evaluated');
create type analysis_state as enum ('draft', 'published');
create type job_status as enum
  ('queued', 'running', 'succeeded', 'failed', 'partial');
create type cost_status as enum ('projected', 'actual');
create type cost_phase as enum ('acquisition', 'preparation', 'sale');
create type cost_calculation_mode as enum ('fixed', 'rate');
create type cost_basis as enum ('purchase_price', 'sale_price');
create type cost_kind as enum
  ('buyer_fee', 'seller_fee', 'shipping_in', 'shipping_out', 'insurance',
   'customs', 'acquisition_tax', 'sale_tax', 'fx', 'authentication',
   'service', 'repair', 'battery', 'polishing', 'accessory', 'packaging',
   'other');
create type platform_access_method as enum
  ('manual', 'assisted_import', 'official_api', 'partner');
create type ledger_entry_kind as enum
  ('capital_contribution', 'withdrawal', 'purchase_payment', 'cost_payment',
   'sale_receipt', 'refund', 'positive_adjustment', 'negative_adjustment');

create table users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  created_at timestamptz not null default now()
);

create table portfolios (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  base_currency char(3) not null default 'EUR',
  created_at timestamptz not null default now(),
  check (base_currency = upper(base_currency))
);

create table portfolio_members (
  portfolio_id uuid not null references portfolios(id),
  user_id uuid not null references users(id),
  role text not null check (role in ('owner', 'editor', 'viewer')),
  primary key (portfolio_id, user_id)
);

-- rate = quote_currency pour 1 base_currency.
-- Les conversions KAIROS utilisent des lignes quote_currency='EUR'.
create table fx_rates (
  id uuid primary key default gen_random_uuid(),
  base_currency char(3) not null,
  quote_currency char(3) not null default 'EUR',
  rate numeric(24,12) not null check (rate > 0),
  observed_at timestamptz not null,
  source_name text not null,
  created_at timestamptz not null default now(),
  unique (base_currency, quote_currency, observed_at, source_name),
  check (base_currency = upper(base_currency)),
  check (quote_currency = upper(quote_currency))
);

create table rulesets (
  id uuid primary key default gen_random_uuid(),
  version text not null unique,
  config jsonb not null,
  checksum_sha256 text not null unique
    check (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  valid_from timestamptz not null,
  created_by_user_id uuid references users(id),
  created_at timestamptz not null default now()
);

create table strategies (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  name text not null,
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  unique (portfolio_id, name)
);

create table strategy_versions (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  strategy_id uuid not null references strategies(id),
  version integer not null check (version > 0),
  ruleset_id uuid not null references rulesets(id),
  valid_from timestamptz not null,
  minimum_roi numeric(18,10) not null default 0.10
    check (minimum_roi >= 0),
  minimum_profit_eur numeric(16,2) not null default 200
    check (minimum_profit_eur >= 0),
  maximum_allocation_rate numeric(18,10) not null default 0.50
    check (maximum_allocation_rate > 0 and maximum_allocation_rate <= 1),
  negotiation_buffer numeric(18,10) not null default 0.08
    check (negotiation_buffer >= 0),
  settings jsonb not null default '{}'::jsonb,
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  unique (strategy_id, version)
);

create table platforms (
  id uuid primary key,
  code text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table platform_rules (
  id uuid primary key default gen_random_uuid(),
  platform_id uuid not null references platforms(id),
  region_code text not null default '*',
  version integer not null check (version > 0),
  valid_from timestamptz not null,
  valid_to timestamptz,

  access_method platform_access_method not null default 'manual',
  access_authorized boolean not null default false,
  min_poll_interval interval,
  max_poll_interval interval,

  buyer_fee_rate numeric(18,10),
  buyer_fee_fixed numeric(16,2),
  buyer_fee_currency char(3),
  buyer_fee_basis text,
  buyer_fee_min numeric(16,2),
  buyer_fee_max numeric(16,2),

  seller_fee_rate numeric(18,10),
  seller_fee_fixed numeric(16,2),
  seller_fee_currency char(3),
  seller_fee_basis text,
  seller_fee_min numeric(16,2),
  seller_fee_max numeric(16,2),

  payment_rules jsonb not null default '{}'::jsonb,
  shipping_rules jsonb not null default '{}'::jsonb,
  protection_rules jsonb not null default '{}'::jsonb,
  tax_rules jsonb not null default '{}'::jsonb,
  can_observe_active_listing boolean not null default true,
  can_observe_auction_result boolean not null default false,
  can_observe_realized_sale boolean not null default false,
  provenance_url text,
  verified_at timestamptz,
  created_by_user_id uuid references users(id),
  created_at timestamptz not null default now(),

  unique (platform_id, region_code, version),
  exclude using gist (
    platform_id with =,
    region_code with =,
    tstzrange(valid_from, valid_to, '[)') with &&
  ),
  check (valid_to is null or valid_to > valid_from),
  check (buyer_fee_rate is null or buyer_fee_rate >= 0),
  check (seller_fee_rate is null or seller_fee_rate >= 0),
  check (buyer_fee_fixed is null or buyer_fee_fixed >= 0),
  check (seller_fee_fixed is null or seller_fee_fixed >= 0),
  check (buyer_fee_min is null or buyer_fee_min >= 0),
  check (buyer_fee_max is null or buyer_fee_max >= 0),
  check (seller_fee_min is null or seller_fee_min >= 0),
  check (seller_fee_max is null or seller_fee_max >= 0),
  check (buyer_fee_min is null or buyer_fee_max is null or buyer_fee_min <= buyer_fee_max),
  check (seller_fee_min is null or seller_fee_max is null or seller_fee_min <= seller_fee_max),
  check (buyer_fee_fixed is null or buyer_fee_currency is not null),
  check (seller_fee_fixed is null or seller_fee_currency is not null),
  check (not access_authorized or verified_at is not null)
);

create table watch_references (
  id uuid primary key default gen_random_uuid(),
  brand text not null,
  model text,
  reference text not null,
  attributes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (brand, reference)
);

create table watches (
  id uuid primary key default gen_random_uuid(),
  reference_id uuid references watch_references(id),
  reference_status reference_confirmation_status not null default 'unconfirmed',
  identification_confidence numeric(7,4)
    check (identification_confidence between 0 and 100),
  reference_confirmed_by_user_id uuid references users(id),
  reference_confirmed_at timestamptz,
  serial_number_encrypted bytea,
  condition_data jsonb not null default '{}'::jsonb,
  completeness_data jsonb not null default '{}'::jsonb,
  raw_input jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (
    (reference_status in ('confirmed', 'corrected')
      and reference_id is not null
      and reference_confirmed_by_user_id is not null
      and reference_confirmed_at is not null)
    or reference_status not in ('confirmed', 'corrected')
  )
);

create table sellers (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  platform_id uuid references platforms(id),
  external_id text,
  seller_type text,
  country_code char(2),
  reliability_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index sellers_external_identity_uq
  on sellers (portfolio_id, platform_id, external_id)
  where external_id is not null;

create table listings (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  platform_id uuid not null references platforms(id),
  seller_id uuid references sellers(id),
  watch_id uuid not null references watches(id),
  external_id text,
  canonical_url text not null,
  status listing_status not null default 'unknown',
  first_seen_at timestamptz not null default now(),
  last_success_at timestamptz,
  created_at timestamptz not null default now()
);

create unique index listings_external_id_uq
  on listings (portfolio_id, platform_id, external_id)
  where external_id is not null;
create unique index listings_canonical_url_uq
  on listings (portfolio_id, canonical_url);

create table listing_observations (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  listing_id uuid not null references listings(id),
  collection_id uuid not null default gen_random_uuid(),
  observed_at timestamptz not null,
  status listing_status not null,
  reserve_met boolean,
  auction_end_at timestamptz,
  condition_data jsonb not null default '{}'::jsonb,
  completeness_data jsonb not null default '{}'::jsonb,
  raw_data jsonb not null default '{}'::jsonb,
  fetch_status text not null default 'success'
    check (fetch_status in ('success', 'partial', 'failed')),
  error_code text,
  error_message text,
  created_at timestamptz not null default now(),
  unique (listing_id, collection_id)
);

create table listing_observation_prices (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  observation_id uuid not null references listing_observations(id),
  kind price_kind not null,
  amount_source numeric(16,2) not null check (amount_source >= 0),
  currency char(3) not null,
  amount_eur numeric(16,2) not null check (amount_eur >= 0),
  rate_to_eur numeric(24,12) not null check (rate_to_eur > 0),
  fx_rate_at timestamptz not null,
  fx_source text not null,
  fx_rate_id uuid references fx_rates(id),
  created_at timestamptz not null default now(),
  unique (observation_id, kind),
  check (kind <> 'kairos_estimate'),
  check (amount_eur = round(amount_source * rate_to_eur, 2)),
  check (currency <> 'EUR' or rate_to_eur = 1),
  check (currency = 'EUR' or fx_rate_id is not null)
);

create table opportunities (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  created_by_user_id uuid not null references users(id),
  source_mode opportunity_source_mode not null,
  manual_identifier text,
  listing_id uuid references listings(id),
  watch_id uuid not null references watches(id),
  seller_id uuid references sellers(id),
  strategy_id uuid references strategies(id),
  status opportunity_status not null default 'watching',
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (source_mode = 'manual' and listing_id is null and manual_identifier is not null)
    or
    (source_mode <> 'manual' and listing_id is not null and manual_identifier is null)
  )
);

create unique index opportunities_manual_identifier_uq
  on opportunities (portfolio_id, manual_identifier)
  where manual_identifier is not null;
create unique index opportunities_listing_uq
  on opportunities (portfolio_id, listing_id)
  where listing_id is not null;

create table opportunity_price_inputs (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null references opportunities(id),
  kind price_kind not null,
  amount_source numeric(16,2),
  currency char(3),
  amount_eur numeric(16,2),
  rate_to_eur numeric(24,12),
  fx_rate_at timestamptz,
  fx_source text,
  fx_rate_id uuid references fx_rates(id),
  missing_reason text,
  observed_at timestamptz not null default now(),
  actor_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  check (kind in ('asking', 'offer', 'accepted_offer', 'current_bid', 'hammer')),
  check (
    (amount_source is not null
      and amount_source >= 0
      and currency is not null
      and amount_eur is not null
      and amount_eur >= 0
      and rate_to_eur is not null
      and rate_to_eur > 0
      and fx_rate_at is not null
      and fx_source is not null
      and missing_reason is null)
    or
    (amount_source is null
      and currency is null
      and amount_eur is null
      and rate_to_eur is null
      and fx_rate_at is null
      and fx_source is null
      and fx_rate_id is null
      and missing_reason is not null)
  ),
  check (
    amount_source is null
    or amount_eur = round(amount_source * rate_to_eur, 2)
  ),
  check (currency is null or currency <> 'EUR' or rate_to_eur = 1),
  check (currency is null or currency = 'EUR' or fx_rate_id is not null)
);

create table reference_confirmations (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null references opportunities(id),
  watch_id uuid not null references watches(id),
  status reference_confirmation_status not null,
  reference_id uuid references watch_references(id),
  identification_confidence numeric(7,4)
    check (identification_confidence between 0 and 100),
  actor_user_id uuid not null references users(id),
  reason text not null,
  occurred_at timestamptz not null default now(),
  check (length(trim(reason)) > 0),
  check (
    (status in ('confirmed', 'corrected') and reference_id is not null)
    or status not in ('confirmed', 'corrected')
  )
);

create table opportunity_events (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null references opportunities(id),
  actor_user_id uuid references users(id),
  event_type text not null,
  from_status opportunity_status,
  to_status opportunity_status,
  reason text not null,
  payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  check (length(trim(reason)) > 0)
);

create table audit_events (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  actor_user_id uuid references users(id),
  resource_type text not null,
  resource_id uuid not null,
  action text not null,
  reason text not null,
  before_data jsonb,
  after_data jsonb,
  request_id uuid,
  occurred_at timestamptz not null default now(),
  check (length(trim(reason)) > 0),
  check (
    action not in ('correct', 'exclude', 'reinstate')
    or after_data is not null
  )
);

create table comparables (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  reference_id uuid not null references watch_references(id),
  listing_id uuid references listings(id),
  source_name text not null,
  source_external_id text,
  seller_fingerprint text,
  price_kind price_kind not null,
  amount_source numeric(16,2) not null check (amount_source >= 0),
  currency char(3) not null,
  amount_eur numeric(16,2) not null check (amount_eur >= 0),
  rate_to_eur numeric(24,12) not null check (rate_to_eur > 0),
  fx_rate_at timestamptz not null,
  fx_source text not null,
  fx_rate_id uuid references fx_rates(id),
  buyer_variable_fee_eur numeric(16,2) not null default 0
    check (buyer_variable_fee_eur >= 0),
  buyer_fixed_fee_eur numeric(16,2) not null default 0
    check (buyer_fixed_fee_eur >= 0),
  compulsory_shipping_eur numeric(16,2) not null default 0
    check (compulsory_shipping_eur >= 0),
  buyer_total_price_eur numeric(16,2) not null
    check (buyer_total_price_eur >= 0),
  market_status listing_status not null,
  listed_at timestamptz,
  ended_at timestamptz,
  observed_at timestamptz not null,
  source_reliability source_reliability_level not null,
  condition_data jsonb not null default '{}'::jsonb,
  completeness_data jsonb not null default '{}'::jsonb,
  raw_data jsonb not null default '{}'::jsonb,
  created_by_user_id uuid references users(id),
  created_at timestamptz not null default now(),
  check (price_kind <> 'kairos_estimate'),
  check (amount_eur = round(amount_source * rate_to_eur, 2)),
  check (currency <> 'EUR' or rate_to_eur = 1),
  check (currency = 'EUR' or fx_rate_id is not null),
  check (ended_at is null or listed_at is null or ended_at >= listed_at)
);

create unique index comparables_source_identity_uq
  on comparables (portfolio_id, source_name, source_external_id, price_kind)
  where source_external_id is not null;

create table comparable_overrides (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  comparable_id uuid not null references comparables(id),
  previous_override_id uuid references comparable_overrides(id),
  excluded boolean not null,
  exclusion_reason text,
  corrected_data jsonb not null default '{}'::jsonb,
  actor_user_id uuid not null references users(id),
  reason text not null,
  created_at timestamptz not null default now(),
  unique (previous_override_id),
  check (not excluded or exclusion_reason is not null)
);

create table market_valuations (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null references opportunities(id),
  ruleset_id uuid not null references rulesets(id),
  calculated_at timestamptz not null default now(),
  low_value_eur numeric(16,2) not null,
  central_value_eur numeric(16,2) not null,
  high_value_eur numeric(16,2) not null,
  valuation_confidence numeric(7,4) not null
    check (valuation_confidence between 0 and 100),
  trend text,
  ruleset_snapshot jsonb not null,
  explanation jsonb not null default '{}'::jsonb,
  check (low_value_eur <= central_value_eur),
  check (central_value_eur <= high_value_eur)
);

create table valuation_comparables (
  valuation_id uuid not null references market_valuations(id),
  comparable_id uuid not null references comparables(id),
  source_amount_snapshot numeric(16,2) not null,
  source_currency_snapshot char(3) not null,
  amount_eur_snapshot numeric(16,2) not null,
  buyer_total_price_eur numeric(16,2) not null,
  comparable_set_premium numeric(18,10) not null,
  target_set_premium numeric(18,10) not null,
  adjusted_price_eur numeric(16,2) not null,
  source_reliability_factor numeric(18,12) not null,
  recency_factor numeric(18,12) not null,
  reference_factor numeric(18,12) not null,
  condition_factor numeric(18,12) not null,
  completeness_factor numeric(18,12) not null,
  seller_independence_factor numeric(18,12) not null,
  final_weight numeric(24,16) not null check (final_weight >= 0),
  anomaly_flag boolean not null default false,
  excluded boolean not null default false,
  exclusion_reason text,
  trace jsonb not null default '{}'::jsonb,
  primary key (valuation_id, comparable_id),
  check (source_reliability_factor between 0 and 1),
  check (recency_factor between 0 and 1),
  check (reference_factor between 0 and 1),
  check (condition_factor between 0 and 1),
  check (completeness_factor between 0 and 1),
  check (seller_independence_factor between 0 and 1),
  check (not excluded or exclusion_reason is not null)
);

create table analyses (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null references opportunities(id),
  valuation_id uuid references market_valuations(id),
  previous_analysis_id uuid references analyses(id),
  ruleset_id uuid not null references rulesets(id),
  strategy_version_id uuid references strategy_versions(id),
  platform_rule_id uuid references platform_rules(id),
  trigger_type text not null,
  state analysis_state not null default 'draft',
  calculated_at timestamptz not null default now(),
  published_at timestamptz,

  current_price_eur numeric(16,2),
  total_cost_eur numeric(16,2),
  expected_sale_price_eur numeric(16,2),
  raw_max_purchase_price_eur numeric(16,8),
  max_purchase_price_eur numeric(16,2),
  expected_profit_eur numeric(16,2),
  expected_roi numeric(18,10),
  expected_days_to_sell integer,
  score numeric(7,4) check (score between 0 and 100),
  evidence_quality_score numeric(7,4)
    check (evidence_quality_score between 0 and 100),
  recommendation recommendation not null,

  gates jsonb not null default '[]'::jsonb,
  pillars jsonb,
  scenario_results jsonb,
  caps jsonb not null default '[]'::jsonb,
  explanation jsonb not null default '{}'::jsonb,
  ruleset_snapshot jsonb not null,
  strategy_snapshot jsonb,
  platform_rule_snapshot jsonb,
  portfolio_snapshot jsonb,

  check (
    (state = 'draft' and published_at is null)
    or (state = 'published' and published_at is not null)
  ),
  check (
    score is null
    or (
      valuation_id is not null
      and strategy_version_id is not null
      and current_price_eur is not null
      and total_cost_eur is not null
      and expected_sale_price_eur is not null
      and max_purchase_price_eur is not null
      and expected_profit_eur is not null
      and expected_roi is not null
      and pillars is not null
      and scenario_results is not null
    )
  ),
  check (recommendation not in ('buy', 'watch') or score is not null)
);

create unique index analyses_previous_child_uq
  on analyses (previous_analysis_id)
  where previous_analysis_id is not null;

create table opportunity_costs (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null references opportunities(id),
  analysis_id uuid references analyses(id),
  phase cost_phase not null,
  kind cost_kind not null,
  status cost_status not null,
  calculation_mode cost_calculation_mode not null,
  basis cost_basis,

  amount_low_source numeric(16,2),
  amount_central_source numeric(16,2),
  amount_high_source numeric(16,2),
  currency char(3),
  amount_low_eur numeric(16,2),
  amount_central_eur numeric(16,2),
  amount_high_eur numeric(16,2),
  rate_to_eur numeric(24,12),
  fx_rate_at timestamptz,
  fx_source text,
  fx_rate_id uuid references fx_rates(id),

  rate_low numeric(18,10),
  rate_central numeric(18,10),
  rate_high numeric(18,10),

  incurred_at timestamptz,
  provenance text,
  notes text,
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),

  check (
    (calculation_mode = 'fixed'
      and basis is null
      and amount_low_source is not null
      and amount_central_source is not null
      and amount_high_source is not null
      and currency is not null
      and amount_low_eur is not null
      and amount_central_eur is not null
      and amount_high_eur is not null
      and rate_to_eur is not null
      and fx_rate_at is not null
      and fx_source is not null
      and rate_low is null and rate_central is null and rate_high is null)
    or
    (calculation_mode = 'rate'
      and basis is not null
      and rate_low is not null
      and rate_central is not null
      and rate_high is not null
      and amount_low_source is null
      and amount_central_source is null
      and amount_high_source is null)
  ),
  check (
    calculation_mode <> 'fixed'
    or (
      amount_low_source <= amount_central_source
      and amount_central_source <= amount_high_source
      and amount_low_eur <= amount_central_eur
      and amount_central_eur <= amount_high_eur
      and amount_low_eur = round(amount_low_source * rate_to_eur, 2)
      and amount_central_eur = round(amount_central_source * rate_to_eur, 2)
      and amount_high_eur = round(amount_high_source * rate_to_eur, 2)
    )
  ),
  check (
    calculation_mode <> 'rate'
    or (rate_low <= rate_central and rate_central <= rate_high and rate_low >= 0)
  ),
  check (currency is null or currency <> 'EUR' or rate_to_eur = 1),
  check (currency is null or currency = 'EUR' or fx_rate_id is not null)
);

create table purchases (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null unique references opportunities(id),
  amount_source numeric(16,2) not null check (amount_source >= 0),
  currency char(3) not null,
  amount_eur numeric(16,2) not null check (amount_eur >= 0),
  rate_to_eur numeric(24,12) not null check (rate_to_eur > 0),
  fx_rate_at timestamptz not null,
  fx_source text not null,
  fx_rate_id uuid references fx_rates(id),
  purchased_at timestamptz not null,
  payment_status text not null default 'paid',
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  check (amount_eur = round(amount_source * rate_to_eur, 2)),
  check (currency <> 'EUR' or rate_to_eur = 1),
  check (currency = 'EUR' or fx_rate_id is not null)
);

create table sale_listings (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null references opportunities(id),
  platform_id uuid references platforms(id),
  asking_amount_source numeric(16,2) not null check (asking_amount_source >= 0),
  currency char(3) not null,
  asking_amount_eur numeric(16,2) not null check (asking_amount_eur >= 0),
  rate_to_eur numeric(24,12) not null check (rate_to_eur > 0),
  fx_rate_at timestamptz not null,
  fx_source text not null,
  fx_rate_id uuid references fx_rates(id),
  listed_at timestamptz not null,
  ended_at timestamptz,
  external_url text,
  status listing_status not null default 'active',
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  check (ended_at is null or ended_at >= listed_at),
  check (asking_amount_eur = round(asking_amount_source * rate_to_eur, 2)),
  check (currency <> 'EUR' or rate_to_eur = 1),
  check (currency = 'EUR' or fx_rate_id is not null)
);

create table sales (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid not null unique references opportunities(id),
  sale_listing_id uuid references sale_listings(id),
  realized_amount_source numeric(16,2) not null check (realized_amount_source >= 0),
  currency char(3) not null,
  realized_amount_eur numeric(16,2) not null check (realized_amount_eur >= 0),
  rate_to_eur numeric(24,12) not null check (rate_to_eur > 0),
  fx_rate_at timestamptz not null,
  fx_source text not null,
  fx_rate_id uuid references fx_rates(id),
  sold_at timestamptz not null,
  payout_received_at timestamptz,
  buyer_reference text,
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  check (payout_received_at is null or payout_received_at >= sold_at),
  check (realized_amount_eur = round(realized_amount_source * rate_to_eur, 2)),
  check (currency <> 'EUR' or rate_to_eur = 1),
  check (currency = 'EUR' or fx_rate_id is not null)
);

create table portfolio_ledger_entries (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  opportunity_id uuid references opportunities(id),
  kind ledger_entry_kind not null,
  amount_source numeric(16,2) not null check (amount_source > 0),
  currency char(3) not null,
  amount_eur numeric(16,2) not null check (amount_eur > 0),
  rate_to_eur numeric(24,12) not null check (rate_to_eur > 0),
  fx_rate_at timestamptz not null,
  fx_source text not null,
  fx_rate_id uuid references fx_rates(id),
  occurred_at timestamptz not null,
  external_reference text,
  notes text,
  actor_user_id uuid not null references users(id),
  created_at timestamptz not null default now(),
  check (amount_eur = round(amount_source * rate_to_eur, 2)),
  check (currency <> 'EUR' or rate_to_eur = 1),
  check (currency = 'EUR' or fx_rate_id is not null)
);

create table idempotency_records (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  idempotency_key text not null check (length(idempotency_key) between 1 and 128),
  request_method text not null,
  request_path text not null,
  request_hash text not null,
  response_status integer,
  response_body jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  unique (portfolio_id, idempotency_key)
);

create table collection_jobs (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  listing_id uuid references listings(id),
  platform_id uuid not null references platforms(id),
  platform_rule_id uuid not null references platform_rules(id),
  status job_status not null default 'queued',
  attempt_count integer not null default 0 check (attempt_count >= 0),
  idempotency_key text not null,
  scheduled_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  error_code text,
  error_message text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (portfolio_id, idempotency_key)
);

create table alerts (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  recipient_user_id uuid not null references users(id),
  opportunity_id uuid not null references opportunities(id),
  analysis_id uuid references analyses(id),
  opportunity_event_id uuid references opportunity_events(id),
  alert_type text not null,
  severity text not null check (severity in ('info', 'warning', 'critical')),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  read_at timestamptz,
  archived_at timestamptz,
  check (analysis_id is not null or opportunity_event_id is not null)
);

create unique index alerts_dedup_uq
  on alerts (
    portfolio_id,
    opportunity_id,
    alert_type,
    coalesce(
      analysis_id,
      opportunity_event_id,
      '00000000-0000-0000-0000-000000000000'::uuid
    )
  );

create table telemetry_events (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references portfolios(id),
  user_id uuid references users(id),
  event_name text not null,
  opportunity_id uuid references opportunities(id),
  occurred_at timestamptz not null default now(),
  allowed_properties jsonb not null default '{}'::jsonb
);

-- Fonctions de protection.

create function reject_all_mutations()
returns trigger
language plpgsql
as $$
begin
  raise exception 'IMMUTABLE_RESOURCE: % is append-only', TG_TABLE_NAME
    using errcode = '55000';
end;
$$;

create function reject_published_analysis_mutation()
returns trigger
language plpgsql
as $$
begin
  if old.published_at is not null then
    raise exception 'IMMUTABLE_RESOURCE: published analysis'
      using errcode = '55000';
  end if;
  if TG_OP = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create function allow_platform_rule_close_only()
returns trigger
language plpgsql
as $$
begin
  if TG_OP = 'DELETE' then
    raise exception 'IMMUTABLE_RESOURCE: platform_rules'
      using errcode = '55000';
  end if;
  if old.valid_to is null
     and new.valid_to is not null
     and new.valid_to > old.valid_from
     and (to_jsonb(new) - 'valid_to') = (to_jsonb(old) - 'valid_to') then
    return new;
  end if;
  raise exception 'IMMUTABLE_RESOURCE: only valid_to may close a platform rule'
    using errcode = '55000';
end;
$$;

create function touch_opportunity()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  new.version = old.version + 1;
  return new;
end;
$$;

create function enforce_authorized_collection_job()
returns trigger
language plpgsql
as $$
declare
  rule_authorized boolean;
  rule_method platform_access_method;
  rule_platform_id uuid;
  rule_valid_from timestamptz;
  rule_valid_to timestamptz;
begin
  select access_authorized, access_method, platform_id, valid_from, valid_to
  into rule_authorized, rule_method, rule_platform_id, rule_valid_from, rule_valid_to
  from platform_rules
  where id = new.platform_rule_id;

  if rule_authorized is distinct from true
     or rule_method = 'manual'
     or rule_platform_id is distinct from new.platform_id
     or new.scheduled_at < rule_valid_from
     or (rule_valid_to is not null and new.scheduled_at >= rule_valid_to) then
    raise exception 'COLLECTOR_NOT_AUTHORIZED'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger opportunities_touch
before update on opportunities
for each row execute function touch_opportunity();

create trigger collection_jobs_authorized
before insert on collection_jobs
for each row execute function enforce_authorized_collection_job();

create trigger analyses_published_immutable
before update or delete on analyses
for each row execute function reject_published_analysis_mutation();

create trigger rulesets_append_only
before update or delete on rulesets
for each row execute function reject_all_mutations();
create trigger strategy_versions_append_only
before update or delete on strategy_versions
for each row execute function reject_all_mutations();
create trigger platform_rules_close_only
before update or delete on platform_rules
for each row execute function allow_platform_rule_close_only();
create trigger listing_observations_append_only
before update or delete on listing_observations
for each row execute function reject_all_mutations();
create trigger listing_observation_prices_append_only
before update or delete on listing_observation_prices
for each row execute function reject_all_mutations();
create trigger opportunity_price_inputs_append_only
before update or delete on opportunity_price_inputs
for each row execute function reject_all_mutations();
create trigger reference_confirmations_append_only
before update or delete on reference_confirmations
for each row execute function reject_all_mutations();
create trigger opportunity_events_append_only
before update or delete on opportunity_events
for each row execute function reject_all_mutations();
create trigger audit_events_append_only
before update or delete on audit_events
for each row execute function reject_all_mutations();
create trigger comparables_append_only
before update or delete on comparables
for each row execute function reject_all_mutations();
create trigger comparable_overrides_append_only
before update or delete on comparable_overrides
for each row execute function reject_all_mutations();
create trigger market_valuations_append_only
before update or delete on market_valuations
for each row execute function reject_all_mutations();
create trigger valuation_comparables_append_only
before update or delete on valuation_comparables
for each row execute function reject_all_mutations();
create trigger portfolio_ledger_entries_append_only
before update or delete on portfolio_ledger_entries
for each row execute function reject_all_mutations();

-- Index de lecture.

create index listing_observations_latest_idx
  on listing_observations (portfolio_id, listing_id, observed_at desc, id desc);
create index opportunity_price_inputs_latest_idx
  on opportunity_price_inputs
  (portfolio_id, opportunity_id, kind, observed_at desc, id desc);
create index comparables_reference_date_idx
  on comparables (portfolio_id, reference_id, observed_at desc, id desc);
create index analyses_opportunity_date_idx
  on analyses (portfolio_id, opportunity_id, calculated_at desc, id desc);
create index opportunity_events_date_idx
  on opportunity_events (portfolio_id, opportunity_id, occurred_at desc, id desc);
create index audit_events_resource_idx
  on audit_events (portfolio_id, resource_type, resource_id, occurred_at desc);
create index opportunity_costs_status_idx
  on opportunity_costs (portfolio_id, opportunity_id, status, phase, kind);
create index ledger_portfolio_date_idx
  on portfolio_ledger_entries (portfolio_id, occurred_at desc, id desc);
create index collection_jobs_scheduled_idx
  on collection_jobs (status, scheduled_at);
create index alerts_unread_idx
  on alerts (portfolio_id, recipient_user_id, read_at, created_at desc);

-- Les clés composées empêchent une relation entre deux portefeuilles.

create unique index sellers_portfolio_identity_uq
  on sellers (portfolio_id, id);
create unique index strategies_portfolio_identity_uq
  on strategies (portfolio_id, id);
create unique index strategy_versions_portfolio_identity_uq
  on strategy_versions (portfolio_id, id);
create unique index listings_portfolio_identity_uq
  on listings (portfolio_id, id);
create unique index listings_portfolio_watch_identity_uq
  on listings (portfolio_id, id, watch_id);
create unique index listing_observations_portfolio_identity_uq
  on listing_observations (portfolio_id, id);
create unique index opportunities_portfolio_identity_uq
  on opportunities (portfolio_id, id);
create unique index opportunities_portfolio_watch_identity_uq
  on opportunities (portfolio_id, id, watch_id);
create unique index opportunity_events_portfolio_identity_uq
  on opportunity_events (portfolio_id, id);
create unique index comparables_portfolio_identity_uq
  on comparables (portfolio_id, id);
create unique index market_valuations_portfolio_identity_uq
  on market_valuations (portfolio_id, id);
create unique index analyses_portfolio_identity_uq
  on analyses (portfolio_id, id);
create unique index sale_listings_portfolio_identity_uq
  on sale_listings (portfolio_id, id);

alter table listings
  add constraint listings_seller_same_portfolio_fk
  foreign key (portfolio_id, seller_id)
  references sellers (portfolio_id, id);
alter table strategy_versions
  add constraint strategy_versions_strategy_same_portfolio_fk
  foreign key (portfolio_id, strategy_id)
  references strategies (portfolio_id, id);
alter table listing_observations
  add constraint observations_listing_same_portfolio_fk
  foreign key (portfolio_id, listing_id)
  references listings (portfolio_id, id);
alter table listing_observation_prices
  add constraint observation_prices_same_portfolio_fk
  foreign key (portfolio_id, observation_id)
  references listing_observations (portfolio_id, id);
alter table opportunities
  add constraint opportunities_listing_same_portfolio_fk
  foreign key (portfolio_id, listing_id)
  references listings (portfolio_id, id);
alter table opportunities
  add constraint opportunities_listing_watch_match_fk
  foreign key (portfolio_id, listing_id, watch_id)
  references listings (portfolio_id, id, watch_id);
alter table opportunities
  add constraint opportunities_seller_same_portfolio_fk
  foreign key (portfolio_id, seller_id)
  references sellers (portfolio_id, id);
alter table opportunities
  add constraint opportunities_strategy_same_portfolio_fk
  foreign key (portfolio_id, strategy_id)
  references strategies (portfolio_id, id);
alter table opportunity_price_inputs
  add constraint price_inputs_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table reference_confirmations
  add constraint confirmations_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table reference_confirmations
  add constraint confirmations_opportunity_watch_match_fk
  foreign key (portfolio_id, opportunity_id, watch_id)
  references opportunities (portfolio_id, id, watch_id);
alter table opportunity_events
  add constraint events_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table comparables
  add constraint comparables_listing_same_portfolio_fk
  foreign key (portfolio_id, listing_id)
  references listings (portfolio_id, id);
alter table comparable_overrides
  add constraint overrides_comparable_same_portfolio_fk
  foreign key (portfolio_id, comparable_id)
  references comparables (portfolio_id, id);
alter table market_valuations
  add constraint valuations_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table analyses
  add constraint analyses_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table analyses
  add constraint analyses_valuation_same_portfolio_fk
  foreign key (portfolio_id, valuation_id)
  references market_valuations (portfolio_id, id);
alter table analyses
  add constraint analyses_strategy_version_same_portfolio_fk
  foreign key (portfolio_id, strategy_version_id)
  references strategy_versions (portfolio_id, id);
alter table opportunity_costs
  add constraint costs_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table opportunity_costs
  add constraint costs_analysis_same_portfolio_fk
  foreign key (portfolio_id, analysis_id)
  references analyses (portfolio_id, id);
alter table purchases
  add constraint purchases_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table sale_listings
  add constraint sale_listings_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table sales
  add constraint sales_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table sales
  add constraint sales_listing_same_portfolio_fk
  foreign key (portfolio_id, sale_listing_id)
  references sale_listings (portfolio_id, id);
alter table portfolio_ledger_entries
  add constraint ledger_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table collection_jobs
  add constraint jobs_listing_same_portfolio_fk
  foreign key (portfolio_id, listing_id)
  references listings (portfolio_id, id);
alter table alerts
  add constraint alerts_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);
alter table alerts
  add constraint alerts_analysis_same_portfolio_fk
  foreign key (portfolio_id, analysis_id)
  references analyses (portfolio_id, id);
alter table alerts
  add constraint alerts_event_same_portfolio_fk
  foreign key (portfolio_id, opportunity_event_id)
  references opportunity_events (portfolio_id, id);
alter table telemetry_events
  add constraint telemetry_opportunity_same_portfolio_fk
  foreign key (portfolio_id, opportunity_id)
  references opportunities (portfolio_id, id);

-- Seeds déterministes.

insert into platforms (id, code, name) values
  ('00000000-0000-0000-0000-000000000001', 'chrono24', 'Chrono24'),
  ('00000000-0000-0000-0000-000000000002', 'catawiki', 'Catawiki'),
  ('00000000-0000-0000-0000-000000000003', 'vestiaire_collective', 'Vestiaire Collective'),
  ('00000000-0000-0000-0000-000000000004', 'watchcharts', 'WatchCharts'),
  ('00000000-0000-0000-0000-000000000005', 'watchfinder', 'Watchfinder'),
  ('00000000-0000-0000-0000-000000000006', 'independent_boutique', 'Boutique indépendante'),
  ('00000000-0000-0000-0000-000000000007', 'user_data', 'Donnée utilisateur')
on conflict (id) do nothing;

with seed(version, config, valid_from) as (
  values (
    '1.0.0',
    '{
      "gates": {
        "indicative_identification_min": 80,
        "valuation_min_comparables": 2,
        "buy_min_comparables_with_ab": 3,
        "buy_min_comparables_only_c": 4
      },
      "verdict": {
        "buy_score": 75,
        "watch_score": 55,
        "watch_price_ratio": 1.10,
        "minimum_valuation_confidence_for_buy": 60,
        "precedence": ["pass", "analysis_impossible", "watch", "buy"]
      },
      "comparable": {
        "set_premium": {
          "watch_only": 0,
          "box_or_papers": 0.10,
          "full_set": 0.20
        },
        "source_reliability": {
          "a": 1.00, "b": 0.85, "c": 0.65, "d": 0.40, "e": 0.15
        },
        "recency": {
          "days_30": 1.00,
          "days_90": 0.90,
          "days_180": 0.75,
          "days_365": 0.55,
          "older": 0.35
        },
        "reference": {"same": 1.00, "close": 0.60},
        "condition": {"one_level": 1.00, "two_levels": 0.70, "unknown": 0.50},
        "completeness": {"same": 1.00, "one_level": 0.80, "unknown": 0.60},
        "seller_independence": {"independent": 1.00, "probable_duplicate": 0.20},
        "outlier": {
          "minimum_count": 4,
          "mad_scale": 1.4826,
          "modified_z_threshold": 3.5,
          "iqr_multiplier": 1.5
        }
      },
      "valuation_confidence": {
        "weights": {
          "volume": 0.30,
          "source_reliability": 0.25,
          "recency": 0.20,
          "similarity": 0.15,
          "dispersion": 0.10
        },
        "volume_scores": {"2": 30, "3": 50, "4": 65, "5_7": 80, "8_plus": 100},
        "dispersion_scores": {
          "width_10": 100,
          "width_20": 80,
          "width_30": 60,
          "width_45": 35,
          "wider": 10
        },
        "caps": {
          "no_ab": 65,
          "two_comparables": 55,
          "identity_unconfirmed": 40,
          "single_seller": 35
        },
        "small_sample_interval": 0.10
      },
      "pricing": {
        "negotiation_buffer": 0.08,
        "strong_price_buffer": 0.12,
        "strong_price_days": 14,
        "no_offer_review_days": 30,
        "maximum_solver_ceiling_eur": 1000000,
        "purchase_rounding": {
          "under_2000": 10,
          "from_2000_to_5000": 25,
          "over_5000": 50
        }
      },
      "sale_delay": {
        "minimum_dated_comparables": 5,
        "depth_days": {
          "20_plus": 21,
          "10_19": 35,
          "5_9": 60,
          "3_4": 90,
          "under_3": 180
        },
        "price_multipliers": {
          "at_or_below_low": 0.85,
          "at_or_below_central": 1.00,
          "at_or_below_high": 1.35,
          "above_high": 1.75
        },
        "minimum_days": 7,
        "maximum_days": 365
      },
      "scoring": {
        "pillar_weights": {
          "profitability": 0.30,
          "liquidity": 0.275,
          "portfolio": 0.20,
          "condition": 0.15,
          "evidence_quality": 0.075
        },
        "profitability_subweights": {"profit": 0.60, "roi": 0.40},
        "liquidity_subweights": {"delay": 0.50, "depth": 0.25, "consistency": 0.25},
        "portfolio_subweights": {"cash_impact": 0.40, "diversification": 0.30, "immobilization": 0.30},
        "condition_subweights": {"mechanical": 0.40, "cosmetic": 0.35, "completeness": 0.20, "originality": 0.05},
        "evidence_subweights": {"listing": 0.35, "comparables": 0.30, "seller": 0.20, "protections": 0.15},
        "curves": {
          "profit_eur": [[0, 0], [100, 25], [200, 50], [350, 75], [500, 100]],
          "roi": [[0, 0], [0.05, 25], [0.10, 50], [0.15, 75], [0.20, 100]],
          "delay_days": [[14, 100], [30, 80], [60, 60], [90, 40], [180, 15], [181, 0]],
          "depth": [[2, 15], [3, 40], [5, 60], [10, 80], [20, 100]],
          "cash_impact": [[0.20, 100], [0.35, 80], [0.50, 60], [0.70, 35], [0.70000001, 0]],
          "brand_concentration": [[0.25, 100], [0.40, 70], [0.60, 40], [0.60000001, 10]],
          "capital_immobilization": [[0.30, 100], [0.50, 75], [0.70, 45], [0.70000001, 10]]
        },
        "condition_scores": {
          "mechanical": {"verified": 100, "functional": 75, "unknown": 40, "defect": 10},
          "cosmetic": {"excellent": 100, "very_good": 85, "good": 65, "fair": 40, "poor": 10},
          "completeness": {"full_set": 100, "box_or_papers": 70, "watch_only": 40},
          "originality": {"original": 100, "uncertain": 40, "major_modification": 0}
        },
        "evidence_scores": {
          "seller": {"verified": 100, "strong_history": 80, "unknown": 40, "negative_signals": 10},
          "protections": {"authentication_and_escrow": 100, "one_protection": 70, "limited_recourses": 35, "none": 10}
        },
        "caps": {
          "valuation_below_40": 59,
          "valuation_below_60": 74,
          "evidence_below_40": 59,
          "allocation_exceeded": 54,
          "immobilization_and_allocation": 54
        },
        "strict_allocation": {
          "starts_at": 0.35,
          "minimum_valuation_confidence": 70,
          "minimum_evidence_quality": 65
        },
        "identity_warning_max_verdict": "watch",
        "illiquid_diversification_cap": {"liquidity_below": 40, "cap": 50},
        "immobilization_threshold": 0.70,
        "long_delay_days": 180,
        "long_delay_allocation": 0.50
      },
      "alerts": {
        "price_change_rate": 0.01,
        "price_change_minimum_eur": 10,
        "price_drop_rate": 0.05,
        "auction_hours": [24, 3],
        "no_offer_days": 30
      }
    }'::jsonb,
    '2026-07-28T00:00:00Z'::timestamptz
  )
)
insert into rulesets (version, config, checksum_sha256, valid_from)
select
  version,
  config,
  encode(digest(config::text, 'sha256'), 'hex'),
  valid_from
from seed
on conflict (version) do nothing;
