"""Read-only operator checklist. Configuration is never a live launch certificate."""
import time
from .model_policy import MODEL_POLICIES


def readiness_report(settings, config, pool):
    checks = []

    def add(key, title, state, detail):
        checks.append({'id': key, 'title': title, 'status': state, 'detail': detail})

    add('provider', 'OpenBroker credential', 'configured' if settings.upstream_key else 'blocked',
        'Configured privately; balance and actual inference still require testing.' if settings.upstream_key else 'Configure the dedicated server-side OpenBroker key.')
    add('token', 'Token identity', 'configured' if settings.holder_mint else 'blocked',
        'A mint is configured; verify its creator, supply, program and decimals on-chain.' if settings.holder_mint else 'No mint configured. Do not publish a buy button.')
    threshold_ok = bool(settings.holder_mint) and settings.min_holding_raw > 1
    add('threshold', 'Membership threshold', 'configured' if threshold_ok else 'blocked',
        'A non-placeholder raw-unit threshold is set. Publish its whole-token equivalent before launch.' if threshold_ok else 'Replace the one-base-unit placeholder with an explicit, reviewed holding requirement.')
    add('rpc', 'Solana connection', 'configured' if settings.solana_rpc else 'blocked',
        'Configured, not verified here. Run the private mainnet diagnostic.' if settings.solana_rpc else 'Configure the private Solana RPC endpoint.')
    funded = pool['available_budget_ngonka'] > 0
    add('compute_fund', 'Allocated compute budget', 'configured' if funded else 'blocked',
        'Local allocation exists. It is not proof of the current spendable provider balance.' if funded else 'Verify native GNK was credited to OpenBroker before allocating its working budget.')
    add('reconciliation', 'Uncertain provider costs', 'blocked' if pool['reconciliation_required'] else 'clear',
        'Reconcile outstanding uncertain requests before admitting more traffic.' if pool['reconciliation_required'] else 'No holder-ledger request currently requires cost reconciliation.')
    add('maintenance', 'Traffic switch', 'blocked' if config['maintenance_mode'] else 'clear',
        'Maintenance mode is on.' if config['maintenance_mode'] else 'Maintenance mode is off; other admission checks still apply.')
    add('production', 'Production security', 'configured' if settings.production and settings.origin.startswith('https://') and len(settings.admin_key) >= 32 else 'review',
        'Production mode, HTTPS and admin-secret length are checked. This is not a security audit.')
    full_allowances = config['global_daily_tokens'] // config['holder_daily_tokens']
    add('pool_sizing', 'Shared daily capacity', 'review',
        f'The daily pool covers {full_allowances} complete default wallet allowances, not every holder. Admission must reflect this cap.')
    largest_context = max(m.get('context_length', 0) for m in MODEL_POLICIES.values())
    add('context_vs_allowance', 'Large requests versus allowance', 'review' if largest_context > config['holder_daily_tokens'] else 'clear',
        'A model context ceiling is not a funded allowance. Requests also need enough remaining wallet and global tokens.')
    add('live_inference', 'Real provider acceptance', 'review',
        'Run explicitly authorized paid tests, including streaming, tools and long output. No live test is inferred from configuration.')
    add('holder_farming', 'Membership abuse controls', 'review',
        'Wallets can transfer tokens to farm multiple allowances. A reviewed cooldown or verified non-transferable lock is not implemented.')
    add('payments', 'Payments and staking', 'disabled',
        'Quotes do not mint credits. Staking, payment settlement and treasury execution remain disabled.')
    return {
        'status': 'blocked' if any(c['status'] == 'blocked' for c in checks) else 'review_required',
        'checked_at': time.time(), 'scope': 'Local configuration and accounting only',
        'checks': checks, 'spends_funds': False, 'launch_authorized': False,
        'capacity': {
            'full_allowances_per_day': full_allowances,
            'wallet_daily_ai_tokens': config['holder_daily_tokens'],
            'shared_daily_ai_tokens': config['global_daily_tokens'],
            'default_wallet_day_budget_ngonka': config['holder_daily_tokens'] * config['ngonka_per_token_budget'],
            'local_available_budget_ngonka': pool['available_budget_ngonka'],
        },
        'accounting_notice': 'OpenBroker usage summaries exclude synthetic escrow accounting lines. Reconcile epoch adjustments before calculating operating profit.'
    }
