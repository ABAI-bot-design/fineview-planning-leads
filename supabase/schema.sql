-- Fine View planning leads: CRM foundation

create table if not exists applications (
  id            bigserial primary key,
  council       text not null,
  key_val       text not null,
  reference     text,
  address       text,
  description   text,
  decision      text,
  decision_date text,
  size_score    text check (size_score in ('High','Med')),
  url           text,
  scraped_at    timestamptz default now(),
  unique (council, key_val)
);

create table if not exists contacts (
  id               bigserial primary key,
  name             text not null,
  category         text not null check (category in ('Developer','Builder','Architect-agent','Homeowner')),
  is_business      boolean not null,
  -- business-only enrichment fields (never populated for Homeowner)
  company_number   text,
  company_status   text,
  directors        text[],
  website          text,
  email            text,
  phone            text,
  instagram        text,
  facebook         text,
  linkedin         text,
  postal_address   text,
  -- outreach state
  sequence_step    int default 0,
  next_touch_at    date,
  status           text default 'new' check (status in ('new','in_sequence','replied','call_booked','quoted','won','lost','unsubscribed')),
  created_at       timestamptz default now(),
  unique (name, category)
);

create table if not exists application_contacts (
  application_id bigint references applications(id) on delete cascade,
  contact_id     bigint references contacts(id) on delete cascade,
  role           text check (role in ('applicant','agent')),
  primary key (application_id, contact_id, role)
);

-- Homeowner letters (consent-first): property address only
create table if not exists letters (
  id             bigserial primary key,
  application_id bigint references applications(id) on delete cascade unique,
  campaign_code  text,
  sent_at        timestamptz,
  stannp_id      text
);

-- Homeowners who opted in via the QR landing page
create table if not exists opt_ins (
  id             bigserial primary key,
  letter_id      bigint references letters(id),
  name           text,
  email          text,
  phone          text,
  instagram      text,
  consent_text   text not null,
  consented_at   timestamptz default now()
);

-- Global suppression: anyone here is never contacted again
create table if not exists suppression (
  email      text primary key,
  reason     text,
  created_at timestamptz default now()
);
