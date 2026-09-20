# Slipvolt API policy — 2026-09-20 research snapshot

Slipvolt is an OpenAI-compatible **Chat Completions** gateway on top of a dedicated OpenBroker account. The upstream account key stays server-side. Customer `sv_` keys are independent, revocable credentials tied to a Solana wallet and one shared wallet allowance.

## Live upstream models and limits

OpenBroker's current public catalog lists:

| Model | Gonka deployed context | Gonka advertised max completion | Slipvolt default output | Slipvolt hard output |
|---|---:|---:|---:|---:|
| `MiniMaxAI/MiniMax-M2.7` | 180,000 | 16,384 | 4,096 | 16,384 |
| `deepseek-ai/DeepSeek-V4-Flash-0731` | 400,000 | 16,384 | 4,096 | 16,384 |
| `zai-org/GLM-5.3-Flash` | 400,000 | 16,384 | 4,096 | 16,384 |

Sources: OpenBroker `/v1/models`; Gonka chain `/models_all`; Gonka proxy `/v1/models`. `context_window` in the governance response is currently zero, so the deployed `--max-model-len` and proxy metadata are used instead.

Slipvolt reads the live OpenBroker catalog and Gonka metadata. An admin can **tighten** the output ceiling but never expand it above 16,384. Large context is capability, not a latency SLA. Applications should leave room for completion tokens inside the model context.

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
- Maximum output: 16,384 tokens.
- `max_tokens` and `max_completion_tokens` are aliases and must agree if both are supplied.
- Maximum JSON nesting depth: 32.
- Live provider health is checked before dispatch; an explicitly unroutable/unavailable model returns 503 without spending holder allowance.
- Standard function tools/tool calls are passed through; Slipvolt does **not execute tools**.
- Compatible Gonka parameters include `logit_bias`, `logprobs`, `structured_outputs`, reasoning/thinking hints, `min_tokens`, `bad_words`, `stop_token_ids`, `skip_special_tokens`, `detokenize`, and bounded chat-template kwargs. Unknown top-level fields remain rejected.
- Streaming uses SSE and requires usage in the terminal stream so allowance settlement can be reconciled.

The gateway fails closed when the live model catalog or spendable OpenBroker balance cannot be verified.

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
