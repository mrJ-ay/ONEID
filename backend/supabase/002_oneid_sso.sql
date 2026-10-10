-- Safe, short-lived, single-use PKCE authorization codes for site SSO.
create schema if not exists oneid_private;
revoke all on schema oneid_private from public, anon, authenticated;
grant usage on schema oneid_private to service_role;

create table if not exists oneid_private.oauth_codes (
    code_hash text primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    client_id text not null,
    redirect_uri text not null,
    code_challenge text not null,
    expires_at timestamptz not null
);
alter table oneid_private.oauth_codes enable row level security;
grant all on oneid_private.oauth_codes to service_role;

create or replace function public.issue_oneid_oauth_code(
    p_code_hash text,
    p_user_id uuid,
    p_client_id text,
    p_redirect_uri text,
    p_code_challenge text,
    p_expires_at timestamptz
) returns void
language plpgsql security definer
set search_path = pg_catalog, oneid_private
as $$
begin
    insert into oneid_private.oauth_codes (code_hash, user_id, client_id, redirect_uri, code_challenge, expires_at)
    values (p_code_hash, p_user_id, p_client_id, p_redirect_uri, p_code_challenge, p_expires_at);
end;
$$;

create or replace function public.redeem_oneid_oauth_code(
    p_code_hash text,
    p_client_id text,
    p_redirect_uri text,
    p_code_challenge text
) returns table(user_id uuid)
language sql security definer
set search_path = pg_catalog, oneid_private
as $$
    delete from oneid_private.oauth_codes as code
    where code.code_hash = p_code_hash
      and code.client_id = p_client_id
      and code.redirect_uri = p_redirect_uri
      and code.code_challenge = p_code_challenge
      and code.expires_at > now()
    returning code.user_id;
$$;

revoke all on function public.issue_oneid_oauth_code(text, uuid, text, text, text, timestamptz) from public, anon, authenticated;
revoke all on function public.redeem_oneid_oauth_code(text, text, text, text) from public, anon, authenticated;
grant execute on function public.issue_oneid_oauth_code(text, uuid, text, text, text, timestamptz) to service_role;
grant execute on function public.redeem_oneid_oauth_code(text, text, text, text) to service_role;

notify pgrst, 'reload schema';
