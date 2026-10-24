"""Conservative local model policy intersected with the live OpenBroker catalog.

Default context/output values are informed by reviewed Gonka documentation and
are local admission caps, not verified OpenBroker serving limits or a
throughput/SLA promise. Separate Gonka proxy observations are retained as
discovery metadata and never raise a reviewed cap.
"""

MODEL_POLICIES = {
    'MiniMaxAI/MiniMax-M2.7': {
        'name':'MiniMax M2.7','company':'MiniMax','category':'Coding & agents',
        'context_length':180_000,'max_completion_tokens':4_096,
        'direct_input_per_million_usd':0.30,'direct_output_per_million_usd':1.20,
        'direct_cached_input_per_million_usd':0.06,
        'direct_source':'https://platform.minimax.io/subscribe/token-plan?tab=api-enterprise',
    },
    'deepseek-ai/DeepSeek-V4-Flash-0731': {
        'name':'DeepSeek V4 Flash · 0731','company':'DeepSeek','category':'Reasoning',
        'context_length':400_000,'max_completion_tokens':4_096,
        # Direct DeepSeek now serves V4.1 Flash; this is a market reference, not same-version pricing.
        'direct_input_per_million_usd':0.15,'direct_output_per_million_usd':0.60,
        'direct_cached_input_per_million_usd':0.003,
        'direct_price_note':'DeepSeek direct reference is current V4.1 Flash off-peak cache-miss pricing; not the same model revision.',
        'direct_source':'https://api-docs.deepseek.com/quick_start/pricing/',
    },
    'zai-org/GLM-5.3-Flash': {
        'name':'GLM 5.3 Flash','company':'Z.ai','category':'General & agents',
        'context_length':400_000,'max_completion_tokens':4_096,
        'direct_input_per_million_usd':0.15,'direct_output_per_million_usd':0.50,
        'direct_cached_input_per_million_usd':0.03,
        'direct_source':'https://docs.z.ai/guides/overview/pricing',
    },
}

DEFAULT_OUTPUT_TOKENS = 4096
REVIEWED_OUTPUT_TOKENS = 4096
MODEL_LIMIT_CEILING = 1_048_576
MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_MESSAGES = 2048
MAX_CHOICES = 5


def snapshot(model_id):
    base = MODEL_POLICIES.get(model_id, {})
    return {'id':model_id, **base,
        'context_length':base.get('context_length'),
        'max_completion_tokens':base.get('max_completion_tokens'),
        'discovered_context_length':None,
        'discovered_max_completion_tokens':None,
        'discovery_limits_status':'unknown',
        'context_limit_source':'reviewed_policy' if base.get('context_length') else None,
        'completion_limit_source':'reviewed_policy' if base.get('max_completion_tokens') else None,
        'operator_override_configured':False,
        'openbroker_limits_verified':False,
        'limits_source':'Conservative reviewed local policy informed by Gonka documentation, optionally tightened by separate Gonka proxy metadata; not a verified OpenBroker serving limit',
        'context_check':'conservative_utf8_admission'}


def merge_upstream_metadata(model_id, metadata, operator_cap=REVIEWED_OUTPUT_TOKENS, operator_override=None):
    row = snapshot(model_id)
    discovered_context = None
    discovered_output = None
    if isinstance(metadata, dict):
        context = metadata.get('context_length')
        output = metadata.get('max_completion_tokens')
        if type(context) is int and context > 0:
            discovered_context = context
        if type(output) is int and output > 0:
            discovered_output = output
    row['discovered_context_length'] = discovered_context
    row['discovered_max_completion_tokens'] = discovered_output
    row['discovery_limits_status'] = ('reported' if discovered_context and discovered_output else
        'partial' if discovered_context or discovered_output else 'unknown')
    if isinstance(operator_override,dict):
        override_context=operator_override.get('context_length')
        override_output=operator_override.get('max_completion_tokens')
        if (type(override_context) is int and type(override_output) is int and
                0<override_output<override_context<=MODEL_LIMIT_CEILING):
            row['context_length']=override_context
            row['max_completion_tokens']=min(override_output,operator_cap)
            row['context_limit_source']='operator_override_unverified'
            row['completion_limit_source']='operator_override_unverified'
            row['operator_override_configured']=True
            row['limits_source']='Explicit operator model-limit override; not a verified OpenBroker serving limit'
            return row
    # Discovery is untrusted capability data. It may make a reviewed cap safer,
    # but it cannot make an unreviewed model usable or raise a reviewed cap.
    reviewed_context = row.get('context_length')
    if reviewed_context and discovered_context and discovered_context < reviewed_context:
        row['context_length'] = discovered_context
        row['context_limit_source'] = 'discovery_tighter_than_reviewed_policy'
    reviewed_output = row.get('max_completion_tokens')
    if reviewed_output:
        effective = min(reviewed_output, operator_cap)
        source = 'operator_cap' if operator_cap < reviewed_output else 'reviewed_policy'
        if discovered_output and discovered_output < effective:
            effective = discovered_output
            source = 'discovery_tighter_than_reviewed_policy'
        row['max_completion_tokens'] = effective
        row['completion_limit_source'] = source
    return row
