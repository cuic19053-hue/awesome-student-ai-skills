"""Real PostgreSQL verification; opt in with RUN_POSTGRES_POLICY_TESTS=1.

Uses an ephemeral, network-isolated container with a preinstalled image. No
production connection, ports, credentials, user data, or image downloads.
"""

import os
from pathlib import Path
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_POLICY_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL billing-policy integration test",
)
@pytest.mark.parametrize("existing_signup_trigger", [False, True])
def test_registration_policy_migration_in_real_postgres(existing_signup_trigger):
    name = "stardust-trial-qa-" + uuid.uuid4().hex[:10]
    subprocess.run(
        ["docker", "run", "--rm", "--pull=never", "--network=none", "--detach",
         "--name", name, "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:15-alpine"],
        check=True, capture_output=True, text=True, timeout=30,
    )

    def sql(source, *, ok=True):
        result = subprocess.run(
            ["docker", "exec", "-i", name, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-Atq"],
            input=source, text=True, capture_output=True, timeout=30,
        )
        if ok:
            assert result.returncode == 0, result.stderr + result.stdout
        else:
            assert result.returncode != 0, "Expected authorization rejection"
        return result.stdout.strip()

    try:
        for _ in range(40):
            ready = subprocess.run(
                # The image's temporary init server only accepts Unix sockets;
                # wait for the final TCP listener, not that transient server.
                ["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                capture_output=True, timeout=5,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("Isolated PostgreSQL failed to start")
        sql("""
          CREATE ROLE anon;
          CREATE ROLE authenticated;
          CREATE ROLE service_role BYPASSRLS;
          CREATE SCHEMA auth;
          CREATE TABLE auth.users (
            id uuid PRIMARY KEY, email text,
            created_at timestamptz NOT NULL DEFAULT now()
          );
          CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid
          $$;
          GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
          CREATE TABLE public.workbench_credit_wallets (
            user_id uuid PRIMARY KEY REFERENCES auth.users(id),
            balance_micro_cny bigint NOT NULL DEFAULT 0,
            total_credited_micro_cny bigint NOT NULL DEFAULT 0,
            total_spent_micro_cny bigint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
          );
          ALTER TABLE public.workbench_credit_wallets ENABLE ROW LEVEL SECURITY;
          GRANT SELECT ON public.workbench_credit_wallets TO authenticated;
          GRANT SELECT, INSERT, UPDATE ON public.workbench_credit_wallets TO service_role;
          CREATE POLICY own_wallet ON public.workbench_credit_wallets
            FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));
          CREATE FUNCTION public.workbench_check_backend(secret text) RETURNS void
          LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
          BEGIN
            IF secret IS DISTINCT FROM repeat('a', 64) THEN
              RAISE EXCEPTION 'invalid backend secret' USING ERRCODE='42501';
            END IF;
          END $$;
          REVOKE ALL ON FUNCTION public.workbench_check_backend(text)
            FROM PUBLIC, anon, authenticated;
        """)
        sql((ROOT / "supabase/migrations/20261015153000_workbench_free_chats_policy.sql").read_text())
        sql("""
          INSERT INTO auth.users(id,email,created_at) VALUES
            ('00000000-0000-0000-0000-000000000001','old@gmail.com','2026-10-01'),
            ('00000000-0000-0000-0000-000000000002','unpaid@gmail.com','2026-10-01'),
            ('00000000-0000-0000-0000-000000000003','recent@gmail.com','2026-10-18 08:51:48+00');
          INSERT INTO public.workbench_credit_wallets
            (user_id,balance_micro_cny,total_credited_micro_cny,total_spent_micro_cny,free_chat_count)
          VALUES
            ('00000000-0000-0000-0000-000000000001',420000,1000000,580000,3),
            ('00000000-0000-0000-0000-000000000002',0,0,0,3),
            ('00000000-0000-0000-0000-000000000003',0,0,0,2);
        """)
        if existing_signup_trigger:
            sql("""
              CREATE TRIGGER on_auth_user_created_welcome_credits
              AFTER INSERT ON auth.users
              FOR EACH ROW EXECUTE FUNCTION public.handle_new_user_welcome_credits();
            """)
        migration = (ROOT / "supabase/migrations/20261018092506_workbench_registration_trial_cutoff.sql").read_text()
        sql(migration)
        sql("""
          DO $$
          BEGIN
            ASSERT (SELECT free_chat_count=0 AND balance_micro_cny=420000
                    AND total_credited_micro_cny=1000000 AND total_spent_micro_cny=580000
                    FROM public.workbench_credit_wallets
                    WHERE user_id='00000000-0000-0000-0000-000000000001');
            ASSERT (SELECT free_chat_count=0 FROM public.workbench_credit_wallets
                    WHERE user_id='00000000-0000-0000-0000-000000000002');
            ASSERT (SELECT free_chat_count=2 FROM public.workbench_credit_wallets
                    WHERE user_id='00000000-0000-0000-0000-000000000003');
            ASSERT public.workbench_consume_free_chat('00000000-0000-0000-0000-000000000001')=-1;
            ASSERT public.workbench_refund_free_chat('00000000-0000-0000-0000-000000000002')=0;
          END $$;
          INSERT INTO auth.users(id,email,created_at) VALUES
            ('00000000-0000-0000-0000-000000000004','new@gmail.com','2026-10-18 08:51:49+00'),
            ('00000000-0000-0000-0000-000000000005','edge@gmail.com','2026-10-18 08:51:47+00'),
            ('00000000-0000-0000-0000-000000000006','race@gmail.com','2026-10-18 08:51:49+00'),
            ('00000000-0000-0000-0000-000000000007','missing@gmail.com','2026-10-18 08:51:49+00');
          DO $$
          BEGIN
            ASSERT (SELECT free_chat_count=3 FROM public.workbench_credit_wallets
                    WHERE user_id='00000000-0000-0000-0000-000000000004');
            ASSERT (SELECT free_chat_count=0 FROM public.workbench_credit_wallets
                    WHERE user_id='00000000-0000-0000-0000-000000000005');
            ASSERT public.workbench_consume_free_chat('00000000-0000-0000-0000-000000000004')=2;
            ASSERT public.workbench_refund_free_chat('00000000-0000-0000-0000-000000000004')=3;
          END $$;
          -- Any verified recharge path changes these same wallet fields.
          UPDATE public.workbench_credit_wallets
          SET balance_micro_cny=1000000,total_credited_micro_cny=1000000
          WHERE user_id='00000000-0000-0000-0000-000000000004';
          DO $$
          BEGIN
            ASSERT (SELECT free_chat_count=0 AND balance_micro_cny=1000000
                    FROM public.workbench_credit_wallets
                    WHERE user_id='00000000-0000-0000-0000-000000000004');
            ASSERT public.workbench_refund_free_chat('00000000-0000-0000-0000-000000000004')=0;
          END $$;
          UPDATE public.workbench_credit_wallets
          SET balance_micro_cny=0,total_spent_micro_cny=1000000
          WHERE user_id='00000000-0000-0000-0000-000000000004';
          DO $$
          BEGIN
            ASSERT public.workbench_consume_free_chat('00000000-0000-0000-0000-000000000004')=-1;
            ASSERT public.workbench_refund_free_chat('00000000-0000-0000-0000-000000000004')=0;
          END $$;
          DELETE FROM public.workbench_credit_wallets
          WHERE user_id='00000000-0000-0000-0000-000000000007';
          DO $$
          BEGIN
            ASSERT public.workbench_consume_free_chat('00000000-0000-0000-0000-000000000007')=-1;
            ASSERT NOT EXISTS (SELECT 1 FROM public.workbench_credit_wallets
                    WHERE user_id='00000000-0000-0000-0000-000000000007');
            ASSERT NOT has_function_privilege('anon','public.workbench_consume_free_chat(uuid)','execute');
            ASSERT NOT has_function_privilege('authenticated','public.workbench_refund_free_chat(uuid)','execute');
            ASSERT has_function_privilege('service_role','public.workbench_consume_free_chat(uuid)','execute');
          END $$;
        """)
        # A browser JWT alone cannot mutate free counts, even for its own user.
        sql("""
          SET ROLE authenticated;
          SET request.jwt.claim.sub='00000000-0000-0000-0000-000000000003';
          SELECT public.workbench_consume_free_chat('00000000-0000-0000-0000-000000000003');
        """, ok=False)
        # Backend capability is required and cannot target another account.
        sql("""
          SET ROLE authenticated;
          SET request.jwt.claim.sub='00000000-0000-0000-0000-000000000003';
          SELECT public.workbench_backend_consume_free_chat(
            '00000000-0000-0000-0000-000000000006',repeat('a',64));
        """, ok=False)
        sql("""
          SET ROLE authenticated;
          SET request.jwt.claim.sub='00000000-0000-0000-0000-000000000003';
          SELECT public.workbench_backend_consume_free_chat(
            '00000000-0000-0000-0000-000000000003','wrong-secret');
        """, ok=False)
        assert sql("""
          SET ROLE authenticated;
          SET request.jwt.claim.sub='00000000-0000-0000-0000-000000000003';
          SELECT public.workbench_backend_consume_free_chat(
            '00000000-0000-0000-0000-000000000003',repeat('a',64));
          SELECT count(*) FROM public.workbench_credit_wallets;
        """).splitlines() == ["1", "1"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            remaining = list(pool.map(lambda _: int(sql(
                "SELECT public.workbench_consume_free_chat('00000000-0000-0000-0000-000000000006');"
            )), range(8)))
        assert sorted(remaining) == [-1, -1, -1, -1, -1, 0, 1, 2]
        # Reapplying must not replenish successful free calls or reset balances.
        sql(migration)
        assert sql("""
          SELECT free_chat_count FROM public.workbench_credit_wallets
          WHERE user_id='00000000-0000-0000-0000-000000000003';
          SELECT count(*) FROM pg_catalog.pg_trigger
          WHERE tgrelid='auth.users'::regclass
            AND tgfoid='public.handle_new_user_welcome_credits()'::regprocedure
            AND NOT tgisinternal;
        """).splitlines() == ["1", "1"]
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True, timeout=30, check=True)
