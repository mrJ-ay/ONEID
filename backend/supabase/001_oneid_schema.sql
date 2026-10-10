-- Supabase Auth is the credential/session authority. Passwords are never stored here.
create table if not exists public.oneid_profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    username text not null,
    username_normalized text not null unique,
    nickname text not null,
    auth_login_email text not null unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.oneid_roles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    role text not null default 'user' check (role in ('user', 'admin')),
    granted_at timestamptz not null default now()
);

alter table public.oneid_profiles enable row level security;
alter table public.oneid_roles enable row level security;

-- There are intentionally no browser-side write policies. The FastAPI server
-- uses the service-role key for these tables; never expose that key to the web.
