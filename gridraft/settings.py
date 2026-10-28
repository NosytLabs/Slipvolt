"""Local settings and validation shared by the API and offline setup doctor.

Environment variables are read only when Settings.from_env() is called.
"""
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .gonka import validate_address
from .integrations import validate_endpoint
from .model_policy import (MODEL_POLICIES, DEFAULT_OUTPUT_TOKENS,
                           REVIEWED_OUTPUT_TOKENS, MODEL_LIMIT_CEILING, MAX_BODY_BYTES)
from .security import decode_address


def model_limit_overrides_from_env():
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    def reject_constant(_):raise ValueError('Non-finite JSON number')
    try:
        return json.loads(os.getenv('MODEL_LIMIT_OVERRIDES_JSON','{}'),
            object_pairs_hook=unique_object,parse_constant=reject_constant)
    except (TypeError,json.JSONDecodeError,ValueError) as exc:
        raise ValueError('MODEL_LIMIT_OVERRIDES_JSON must be a JSON object') from exc


@dataclass
class Settings:
    site_name: str = 'Holdbyte'
    origin: str = 'http://127.0.0.1:8000'
    pepper: str = field(default_factory=lambda: secrets.token_hex(32))
    upstream_key: str = ''
    access_mode: str = 'prepaid'
    holder_mint: str = ''
    token_launched: bool = False
    min_holding_raw: int = 1
    solana_rpc: str = ''
    solana_ws: str = ''
    metis_url: str = ''
    zeroex_url: str = ''
    rpc_rps: int = 15
    rpc_concurrency: int = 8
    # Legacy flat rate remains accepted for migration; new installs use split input/output rates.
    retail_nusd_per_token: int | None = None
    retail_input_nusd_per_token: int = 75
    retail_output_nusd_per_token: int = 300
    request_limit: int = 30
    wallet_concurrency: int = 4
    global_request_limit: int = 300
    global_concurrency: int = 50
    default_output_tokens: int = DEFAULT_OUTPUT_TOKENS
    max_output_tokens: int = REVIEWED_OUTPUT_TOKENS
    model_limit_overrides: dict = field(default_factory=dict)
    max_request_bytes: int = MAX_BODY_BYTES
    timeout: int = 180
    admin_key: str = ''
    production: bool = False
    # Safety caps are retail-ledger nano-USD, not an upstream billing guarantee.
    daily_budget_nusd: int = 10_000_000_000
    wallet_daily_budget_nusd: int = 2_000_000_000

    holder_daily_tokens: int = 250000
    global_daily_tokens: int = 1000000
    allowance_ngonka_per_token: int = 25
    public_broker_balance: bool = False
    gonka_treasury_address: str = ''
    holder_token_symbol: str = 'project tokens'
    holder_token_decimals: int = 6

    @classmethod
    def from_env(cls):
        production = os.getenv('APP_ENV','development')=='production'
        pepper = os.getenv('KEY_PEPPER','')
        if production and len(pepper)<32:
            raise ValueError('Set a stable KEY_PEPPER of at least 32 characters')
        return cls(site_name=os.getenv('SITE_NAME','Holdbyte'),origin=os.getenv('APP_ORIGIN','http://127.0.0.1:8000'),
            pepper=pepper or secrets.token_hex(32),upstream_key=os.getenv('OPENBROKER_API_KEY',''),
            access_mode=os.getenv('ACCESS_MODE','holder_allowance'),holder_mint=os.getenv('HOLDER_MINT',''),
            token_launched=os.getenv('TOKEN_LAUNCHED','false')=='true',
            min_holding_raw=int(os.getenv('MIN_HOLDING_RAW','1')),solana_rpc=os.getenv('SOLANA_RPC_URL',''),
            solana_ws=os.getenv('SOLANA_WSS_URL',''),metis_url=os.getenv('METIS_API_URL',''),
            zeroex_url=os.getenv('ZEROX_API_URL',''),rpc_rps=int(os.getenv('SOLANA_RPC_RPS','15')),
            rpc_concurrency=int(os.getenv('SOLANA_RPC_CONCURRENCY','8')),
            retail_nusd_per_token=int(os.environ['RETAIL_NUSD_PER_TOKEN']) if os.getenv('RETAIL_NUSD_PER_TOKEN') else None,
            retail_input_nusd_per_token=int(os.getenv('RETAIL_INPUT_NUSD_PER_TOKEN','75')),
            retail_output_nusd_per_token=int(os.getenv('RETAIL_OUTPUT_NUSD_PER_TOKEN','300')),
            request_limit=int(os.getenv('REQUESTS_PER_MINUTE','30')),
            wallet_concurrency=int(os.getenv('WALLET_CONCURRENCY','4')),
            global_request_limit=int(os.getenv('GLOBAL_REQUESTS_PER_MINUTE','300')),
            global_concurrency=int(os.getenv('GLOBAL_CONCURRENCY','50')),
            default_output_tokens=int(os.getenv('DEFAULT_OUTPUT_TOKENS','4096')),
            max_output_tokens=int(os.getenv('MAX_OUTPUT_TOKENS','4096')),
            model_limit_overrides=model_limit_overrides_from_env(),
            max_request_bytes=int(os.getenv('MAX_REQUEST_BYTES',str(MAX_BODY_BYTES))),
            timeout=int(os.getenv('UPSTREAM_TIMEOUT_SECONDS','180')),
            admin_key=os.getenv('ADMIN_API_KEY',''),production=production,
            daily_budget_nusd=int(os.getenv('DAILY_BUDGET_NUSD','10000000000')),
            wallet_daily_budget_nusd=int(os.getenv('WALLET_DAILY_BUDGET_NUSD','2000000000')),
            holder_daily_tokens=int(os.getenv('HOLDER_DAILY_TOKENS','250000')),
            global_daily_tokens=int(os.getenv('GLOBAL_DAILY_TOKENS','1000000')),
            allowance_ngonka_per_token=int(os.getenv('ALLOWANCE_NGONKA_PER_TOKEN','25')),
            gonka_treasury_address=os.getenv('GONKA_TREASURY_ADDRESS',''),
            public_broker_balance=os.getenv('PUBLIC_BROKER_BALANCE','false').lower()=='true',
            holder_token_symbol=os.getenv('HOLDER_TOKEN_SYMBOL','project tokens'),
            holder_token_decimals=int(os.getenv('HOLDER_TOKEN_DECIMALS','6')))

def validate_settings(settings):
    """Pure configuration validation, shared with the no-I/O setup doctor."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}',settings.site_name):
        raise ValueError('Invalid site name; use 1–40 plain brand characters')
    parsed=urlparse(settings.origin)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('APP_ORIGIN must be an exact origin without a trailing slash')
    if settings.production and parsed.scheme!='https': raise ValueError('Production requires HTTPS')
    if len(settings.pepper)<32: raise ValueError('KEY_PEPPER must be at least 32 characters')
    if settings.access_mode not in ('prepaid','holder','holder_allowance'): raise ValueError('Unknown access mode')
    if type(settings.token_launched) is not bool:
        raise ValueError('Token launch flag must be a boolean')
    if settings.token_launched and (settings.access_mode not in ('holder','holder_allowance') or not settings.holder_mint):
        raise ValueError('Token launch requires a configured holder mint and holder access mode')
    if settings.retail_nusd_per_token is not None:
        if type(settings.retail_nusd_per_token) is not int or not 1<=settings.retail_nusd_per_token<=10**6: raise ValueError('Invalid legacy retail rate')
        settings.retail_input_nusd_per_token=settings.retail_nusd_per_token
        settings.retail_output_nusd_per_token=settings.retail_nusd_per_token
    for rate in (settings.retail_input_nusd_per_token,settings.retail_output_nusd_per_token):
        if type(rate) is not int or not 1<=rate<=10**6: raise ValueError('Invalid retail rate')
    if settings.gonka_treasury_address: validate_address(settings.gonka_treasury_address)
    if settings.min_holding_raw<1: raise ValueError('A positive holder threshold is required')
    for value in (settings.holder_daily_tokens,settings.global_daily_tokens):
        if type(value) is not int or not 1<=value<=10**9: raise ValueError('Invalid token allowance')
    if type(settings.allowance_ngonka_per_token) is not int or not 1<=settings.allowance_ngonka_per_token<=1000000: raise ValueError('Invalid GNK budget rate')
    if not 0<=settings.holder_token_decimals<=18: raise ValueError('Invalid token decimals')
    if len(settings.holder_token_symbol)>30 or not settings.holder_token_symbol.isprintable(): raise ValueError('Invalid token label')
    if settings.access_mode=='holder' or (settings.access_mode=='holder_allowance' and (settings.holder_mint or settings.production)):
        decode_address(settings.holder_mint)
        if not settings.solana_rpc.startswith('https://'): raise ValueError('Holder mode requires an HTTPS RPC URL')
    for value,label,maximum in ((settings.request_limit,'request rate limit',10000),(settings.wallet_concurrency,'wallet concurrency',100),(settings.global_request_limit,'global request rate limit',100000),(settings.global_concurrency,'global concurrency',10000)):
        if type(value) is not int or not 1<=value<=maximum: raise ValueError('Invalid '+label)
    if type(settings.default_output_tokens) is not int or type(settings.max_output_tokens) is not int or not 1<=settings.default_output_tokens<=settings.max_output_tokens<=MODEL_LIMIT_CEILING:
        raise ValueError('Invalid output token limits')
    if not isinstance(settings.model_limit_overrides,dict):raise ValueError('Invalid model limit override configuration')
    for model_id,override in settings.model_limit_overrides.items():
        if (model_id not in MODEL_POLICIES or not isinstance(override,dict) or
                set(override)!={'context_length','max_completion_tokens'}):
            raise ValueError('Invalid model limit override configuration')
        context=override.get('context_length');output=override.get('max_completion_tokens')
        if (type(context) is not int or type(output) is not int or
                not 1<=output<context<=MODEL_LIMIT_CEILING or output>settings.max_output_tokens):
            raise ValueError('Invalid model limit override configuration')
    if type(settings.max_request_bytes) is not int or not 131072<=settings.max_request_bytes<=MAX_BODY_BYTES: raise ValueError('Invalid request body limit')
    if not isinstance(settings.admin_key, str) or (settings.admin_key and (
            len(settings.admin_key) > 512 or not settings.admin_key.isascii()
            or not settings.admin_key.isprintable())):
        raise ValueError('ADMIN_API_KEY must be printable ASCII and at most 512 characters')
    if settings.production and settings.admin_key and len(settings.admin_key)<32: raise ValueError('ADMIN_API_KEY must be at least 32 characters in production')
    for cap in (settings.daily_budget_nusd, settings.wallet_daily_budget_nusd):
        if type(cap) is not int or not 1<=cap<=10**15: raise ValueError('Invalid daily budget')
    for endpoint in (settings.solana_rpc,settings.metis_url,settings.zeroex_url):validate_endpoint(endpoint)
    validate_endpoint(settings.solana_ws,'wss')
    if type(settings.rpc_rps) is not int or not 1<=settings.rpc_rps<=100:raise ValueError('RPC RPS must be 1–100')
    if type(settings.rpc_concurrency) is not int or not 1<=settings.rpc_concurrency<=20:raise ValueError('RPC concurrency must be 1–20')
    return settings
