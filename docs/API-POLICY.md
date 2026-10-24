# Slipvolt API policy — 2026-10-24 research snapshot

Slipvolt is an OpenAI-compatible **Chat Completions** gateway on top of a dedicated OpenBroker account. The upstream account key stays server-side. Customer `sv_` keys are independent, revocable credentials tied to a Solana wallet and one shared wallet allowance.

## Active models and reviewed local limits

OpenBroker's current public catalog lists:

| Model | Reviewed local context | Separate proxy output metadata | Slipvolt default output | Reviewed local output cap |
|---|---:|---:|---:|---:|
| `MiniMaxAI/MiniMax-M2.7` | 180,000 | 16,384 | 4,096 | 16,384 |
| `deepseek-ai/DeepSeek-V4-Flash-0731` | 400,000 | 16,384 | 4,096 | 16,384 |
| `zai-org/GLM-5.3-Flash` | 400,000 | 16,384 | 4,096 | 16,384 |

Sources checked October 24: [OpenBroker catalog](https://openbroker.gonka.gg/docs/models), [Gonka host configuration](https://gonka.ai/docs/host/quickstart/), and [separate Gonka proxy metadata](https://proxy.gonka.gg/v1/models). OpenBroker's own public catalog currently supplies IDs without numeric limits. Zero-valued chain/RPC metadata is unpopulated, not unlimited. The proxy's output field is `max_tokens`; the parser accepts it as an alias of `max_completion_tokens`.

**16,384 is a reviewed local default, not a verified OpenBroker maximum.** The separate proxy and OpenBroker are different serving routes. [OpenBroker chat documentation](https://openbroker.gonka.gg/docs/chat-completions) accepts `max_tokens` without publishing a numeric maximum. Model-native configuration may allow larger windows than Gonka's deployment defaults; neither proves an account-level serving limit. Applications must leave completion headroom inside the context window.

`/api/models` publishes effective `context_length` / `max_completion_tokens`, nullable `discovered_context_length` / `discovered_max_completion_tokens`, a discovery status, and separate source labels. Discovery may tighten reviewed policy but cannot increase it or activate an unknown model. Missing metadata never becomes a fabricated discovered value. The upstream catalog cache is merged with current operator policy on every read.

### Explicit deployment overrides

For a reviewed model, an operator may deliberately configure both limits in the server environment:

```dotenv
MAX_OUTPUT_TOKENS=32768
MODEL_LIMIT_OVERRIDES_JSON={"MiniMaxAI/MiniMax-M2.7":{"context_length":204800,"max_completion_tokens":32768}}
```

This is a configuration example, **not evidence that OpenBroker accepts those limits**. It requires a known model ID, exactly both positive integer fields, `output < context <= 1048576`, and output no larger than the global configured cap. Invalid configuration fails startup. An explicit override replaces separate-proxy tightening for that model and is labelled `operator_override_unverified`; discovered values remain visible. Runtime admin output settings still apply. Without an explicit model override, increasing the global cap alone does not increase a model's reviewed output cap. No override sets `openbroker_limits_verified` to true.

Confirm higher limits from the actual serving operator or a separately authorized, funded boundary test. No paid boundary tests were performed as part of this change.

Previously saved admin settings take precedence over environment defaults for the global output cap. On an existing deployment, check the current admin cap after changing the environment; a saved 16,384 cap will still restrict an explicit 32,768 model override until deliberately updated.

## Admission counting and evidence

The numeric context/output values are a **local policy informed by another Gonka proxy**, not an OpenBroker account benchmark. OpenBroker currently does not publish numeric limits in its own docs. `/api/models` includes `openbroker_limits_verified: false` and `context_check: conservative_utf8_admission`.

Admission uses serialized UTF-8 size plus chat-envelope headroom, not an exact per-model tokenizer. It checks estimated input plus the requested per-choice output against the context policy. It can reject valid tokenized requests early, especially large Unicode/tool payloads; nothing is silently truncated. Exact full-window guarantees require pinned model tokenizers/chat templates and funded account testing.

Budget reservation separately includes **all requested completions**: estimated input + `n × max_tokens`. The maximum output refers to each choice, whereas billable output covers all choices. Admin per-wallet quota overrides and suspension are rechecked transactionally before reservation. Local model metadata reflects changed operator caps even while the upstream catalog is cached.

## Request bounds

Mirrors current Gonka Chat Completions safeguards where practical:

- Body: 10 MiB maximum.
- Messages: 2,048 maximum.
- `n`: 5 maximum.
- Stops: 16 strings, 256 bytes each.
- Default output: 4,096 tokens.
- Default maximum output: 16,384 tokens per choice, subject to effective per-model policy. Explicit operator configuration may change it within the 1,048,576 validation ceiling; that ceiling is not an upstream capability claim.
- `max_tokens` and `max_completion_tokens` are aliases and must agree if both are supplied.
- Maximum JSON nesting depth: 32.
- Live provider health is checked before dispatch; an explicitly unroutable/unavailable model returns 503 without spending holder allowance.
- Standard function tools/tool calls are passed through; Slipvolt does **not execute tools**.
- Compatible Gonka parameters include `logit_bias`, `logprobs`, `structured_outputs`, reasoning/thinking hints, `min_tokens`, `bad_words`, `stop_token_ids`, `skip_special_tokens`, `detokenize`, and bounded chat-template kwargs. Unknown top-level fields remain rejected.
- Streaming uses SSE and requires usage in the terminal stream so allowance settlement can be reconciled.

The gateway fails closed when the live model catalog or spendable OpenBroker balance cannot be verified.

The local GNK reservation is an admission estimate, not a provider-enforced maximum charge. Confirmed settlement can exceed a request's estimate or the locally allocated pool; concurrent requests amplify that exposure. Spendable allowance then shrinks, but this cannot undo provider cost already incurred. Keep provider working capital and acquisition costs reconciled, leave headroom for redundancy/epoch charges, and use a provider-side spending cap if one is actually available. The application does not claim that such an upstream cap has been configured.

## Initial rate limits

Default policy:

- 30 requests/minute per wallet.
- 4 concurrent requests per wallet.
- 300 requests/minute globally.
- 50 concurrent requests globally.

These are operator safety limits, not upstream capacity claims. OpenBroker publishes live capacity separately; the admin console shows it. Wallet/global RPM limits return 429 with `Retry-After`; concurrency limits use a short retry interval; daily allowance exhaustion reports the seconds until the 00:00 UTC reset. Holder responses include `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` (seconds) and wallet scope. The currently configured RPC budget is separate: 15 reads/second with eight reads in flight by default. Raise limits only after observing successful calls, latency and GNK consumption for the deployment.

## Pricing

OpenBroker documents 10 ngonka per token **per attempt** and usually 10–25 effective ngonka per token due to retries/racing (about 15 typical), with additional epoch accounting possible. OpenBroker says its markup is 0%.

The planned Slipvolt metered/overage reference rate is:

- **$0.075 / 1M input tokens**
- **$0.30 / 1M output tokens**

This is not currently a checkout-enabled promise. Holder allowance is funded separately in native GNK. Admin can change the reference rate at runtime.

At an 80/20 input/output mix, that rate produces $0.12 revenue per million total tokens. Therefore **1 billion tokens produces about $120 revenue, not $120,000**. Any profitability model must include volume, GNK/USD acquisition cost, OpenBroker epoch charges, hosting, RPC, support, refunds, taxes and token-launch/treasury expenses.

Market comparison is not apples-to-apples: OpenBroker currently serves DeepSeek V4 Flash 0731 while DeepSeek direct pricing now references V4.1 Flash. Cached direct-provider input can also be cheaper than Slipvolt's proposed input price. Do not market “same model 50% cheaper” without matching the exact revision and cache tier.
