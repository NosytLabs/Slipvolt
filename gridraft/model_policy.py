"""Public model policy grounded in current Gonka/OpenBroker metadata.

Context/output values are upstream capability metadata, not a throughput/SLA promise.
The active catalogue is always intersected with OpenBroker GET /v1/models.
"""

MODEL_POLICIES = {
    'MiniMaxAI/MiniMax-M2.7': {
        'name':'MiniMax M2.7','company':'MiniMax','category':'Coding & agents',
        'context_length':180_000,'max_completion_tokens':16_384,
        'direct_input_per_million_usd':0.30,'direct_output_per_million_usd':1.20,
        'direct_cached_input_per_million_usd':0.06,
        'direct_source':'https://platform.minimax.io/subscribe/token-plan?tab=api-enterprise',
    },
    'deepseek-ai/DeepSeek-V4-Flash-0731': {
        'name':'DeepSeek V4 Flash · 0731','company':'DeepSeek','category':'Reasoning',
        'context_length':400_000,'max_completion_tokens':16_384,
        # Direct DeepSeek now serves V4.1 Flash; this is a market reference, not same-version pricing.
        'direct_input_per_million_usd':0.15,'direct_output_per_million_usd':0.60,
        'direct_cached_input_per_million_usd':0.003,
        'direct_price_note':'DeepSeek direct reference is current V4.1 Flash off-peak cache-miss pricing; not the same model revision.',
        'direct_source':'https://api-docs.deepseek.com/quick_start/pricing/',
    },
    'zai-org/GLM-5.3-Flash': {
        'name':'GLM 5.3 Flash','company':'Z.ai','category':'General & agents',
        'context_length':400_000,'max_completion_tokens':16_384,
        'direct_input_per_million_usd':0.15,'direct_output_per_million_usd':0.50,
        'direct_cached_input_per_million_usd':0.03,
        'direct_source':'https://docs.z.ai/guides/overview/pricing',
    },
}

DEFAULT_OUTPUT_TOKENS = 4096
HARD_OUTPUT_TOKENS = 16384
MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_MESSAGES = 2048
MAX_CHOICES = 5


def snapshot(model_id):
    base = MODEL_POLICIES.get(model_id, {})
    return {'id':model_id, **base, 'openbroker_limits_verified':False, 'limits_source':'Gonka proxy metadata / local policy; not an OpenBroker account benchmark', 'context_check':'conservative_utf8_admission'}


def merge_upstream_metadata(model_id, metadata, operator_cap=HARD_OUTPUT_TOKENS):
    row = snapshot(model_id)
    if isinstance(metadata, dict):
        context = metadata.get('context_length')
        output = metadata.get('max_completion_tokens')
        if type(context) is int and context > 0:
            row['context_length'] = context
        if type(output) is int and output > 0:
            row['max_completion_tokens'] = min(output, operator_cap)
    if 'max_completion_tokens' in row:
        row['max_completion_tokens'] = min(row['max_completion_tokens'], operator_cap)
    return row
