"""Local configuration inspection. No network, database connection or secret output."""
import os
from pathlib import Path
from .app import Settings, validate_settings


def _report(checks):
    return {'status':'blocked' if any(x['status']=='blocked' for x in checks) else 'review_required',
            'scope':'Local configuration only; not provider, wallet or deployment verification',
            'checks':checks,'network_calls':0,'inference_requests':0,'launch_authorized':False}


def invalid_report(code, detail):
    return _report([{'id':code,'title':'Configuration','status':'blocked','detail':detail}])


def report(env_file='.env'):
    checks=[]
    def add(code,title,state,detail):
        checks.append({'id':code,'title':title,'status':state,'detail':detail})
    try:
        if os.getenv('APP_ENV','development') not in ('development','production'):
            return invalid_report('environment_mode','APP_ENV must be development or production.')
        s=Settings.from_env()
        validate_settings(s)
    except (ValueError,TypeError):
        # Exceptions from numeric parsing may include the private value. Never echo them.
        return invalid_report('configuration','Invalid setting. Compare types, origins, endpoint shapes and limits with .env.example.')
    add('stable_pepper','Stable key hashing secret','configured' if len(os.getenv('KEY_PEPPER',''))>=32 else 'blocked',
        'Preserve KEY_PEPPER and the database across restarts. Configuration presence is checked; the value is never printed.')
    add('provider','Dedicated OpenBroker credential','configured' if s.upstream_key else 'blocked',
        'Set OPENBROKER_API_KEY privately. Check its balance separately; no inference was attempted.')
    add('admin','Operator credential','configured' if len(s.admin_key)>=32 and s.admin_key!=s.pepper else 'blocked',
        'Use a separate ADMIN_API_KEY of at least 32 characters, not the pepper or provider key.')
    add('token','Project mint and threshold','configured' if s.holder_mint and s.min_holding_raw>1 else 'blocked',
        'Configure the verified Solana mint, actual decimals and a reviewed raw-unit threshold. One base unit is a placeholder.')
    add('rpc','Solana RPC','configured' if s.solana_rpc else 'blocked',
        'Configure SOLANA_RPC_URL privately, then run the explicit read-only mainnet check.')
    add('https','Production transport','configured' if s.production else 'review',
        'Production requires HTTPS and secure cookies. Development mode is only for local evaluation.')
    try:
        mode=Path(env_file).stat().st_mode
        add('file_permissions','Environment file permissions','review' if mode & 0o077 else 'configured',
            'Keep a local environment file owner-readable only; do not commit it.')
    except OSError:
        add('file_permissions','Environment file','review','No local file inspected. Host-managed environment variables are supported.')
    path=Path(os.getenv('DATABASE_PATH','data/gridraft.db'))
    add('database','Persistent database','review',
        'Existing database file found; integrity, allocations and backups were not inspected.' if path.is_file()
        else 'Database has not been created here. Start one persistent instance; never replace an existing production database.')
    add('funding','Native GNK funding','review','Verify the assigned OpenBroker deposit and spendable balance before allocating its local compute budget.')
    add('live_test','Wallet and inference acceptance','review','A configured key is not a successful request. Run owner-authorized acceptance checks before launch.')
    return _report(checks)
