# Holdbyte API policy — 2026-10-24 research snapshot

Holdbyte is an OpenAI-compatible **Chat Completions** gateway on top of a dedicated OpenBroker account. The upstream account key stays server-side. Customer `sv_` keys are independent, revocable credentials tied to a Solana wallet and one shared wallet allowance. The repository and existing API-key environment names remain Slipvolt for compatibility.

## Active models and reviewed local limits

OpenBroker's current public catalog lists:

| Model | Reviewed local context | Separate proxy output metadata | Holdbyte default output | Reviewed local output cap |
|---|---:|---:|---:|---:|
| `MiniMaxAI/MiniMax-M2.7` | 180,000 | 16,384 | 4,096 | 4,096 |
| `deepseek-ai/DeepSeek-V4-Flash-0731` | 400,000 | 16,384 | 4,096 | 4,096 |
| `zai-org/GLM-5.3-Flash` | 400,000 | 16,384 | 4,096 | 4,096 |

Sources checked October 24: [OpenBroker catalog](https://openbroker.gonka.gg/docs/models), Gonka's [MiniMax](https://gonka.ai/docs/host/minimax-bootstrap/), [DeepSeek](https://gonka.ai/docs/host/deepseek-bootstrap/), and [GLM](https://gonka.ai/docs/host/glm-bootstrap/) deployment instructions, [Gonka FAQ](https://gonka.ai/docs/FAQ/), and [separate Gonka proxy metadata](https://proxy.gonka.gg/v1/models). OpenBroker's own public catalog currently supplies IDs without numeric limits. Zero-valued chain/RPC metadata is unpopulated, not unlimited. The proxy's output field is `max_tokens`; the parser accepts it as an alias of `max_completion_tokens`.

**4,096 is a conservative local default, not a verified OpenBroker maximum or a universal network ceiling.** Gonka's FAQ describes a 4,096 ceiling and observed 3,072-token output on two brokers, but the pinned [DevShard proxy documentation](https://github.com/gonka-ai/gonka/blob/b88062c9529389a61d4ba15b8b5603716a50909e/devshard/docs/proxy.md#L125-L133) calls 3,072 and 4,096 configurable defaults. The [gateway implementation](https://github.com/gonka-ai/gonka/blob/b88062c9529389a61d4ba15b8b5603716a50909e/devshard/cmd/devshardctl/gateway.go#L873-L895) accepts global and per-model overrides, and its [official test](https://github.com/gonka-ai/gonka/blob/b88062c9529389a61d4ba15b8b5603716a50909e/devshard/cmd/devshardctl/gateway_test.go#L855-L915) uses an 8,192 cap. The source is more precise than the FAQ's network-wide wording.

The separate proxy's 16,384 metadata is compatible with an operator override. [OpenBroker chat documentation](https://openbroker.gonka.gg/docs/chat-completions) accepts `max_tokens` without publishing its route's numeric maximum, and its catalog omits the gateway limit fields. No public read-only result establishes this account's deployed cap. Use the shipped 4,096 default conservatively until that route is confirmed; do not advertise 3,072, 4,096, or 16,384 as a measured OpenBroker boundary. A configured upstream gateway may clamp a larger requested output before inference.

The model-native configuration files declare larger positional capacities: [MiniMax](https://huggingface.co/MiniMaxAI/MiniMax-M2.7/blob/main/config.json) 204,800, [DeepSeek](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/blob/main/config.json) 1,048,576, and [GLM](https://huggingface.co/zai-org/GLM-5.3-Flash/blob/main/config.json) 1,048,576. Gonka deploys the lower windows in the table. Context covers input plus completion headroom; it is separate from the output budget. Gonka also documents host-routing limitations on large inputs, so a configured window is not a full-window reliability guarantee.

`/api/models` publishes effective `context_length` / `max_completion_tokens`, nullable `discovered_context_length` / `discovered_max_completion_tokens`, a discovery status, and separate source labels. Discovery may tighten reviewed policy but cannot increase it or activate an unknown model. Missing metadata never becomes a fabricated discovered value. The upstream catalog cache is merged with current operator policy on every read.

### Explicit deployment overrides

For a reviewed model, an operator may deliberately configure both limits in the server environment:

```dotenv
MAX_OUTPUT_TOKENS=32768
MODEL_LIMIT_OVERRIDES_JSON={"MiniMaxAI/MiniMax-M2.7":{"context_length":204800,"max_completion_tokens":32768}}
```

This is a configuration example, **not evidence that OpenBroker accepts those limits**. It requires a known model ID, exactly both positive integer fields, `output < context <= 1048576`, and output no larger than the global configured cap. Invalid configuration fails startup. An explicit override replaces separate-proxy tightening for that model and is labelled `operator_override_unverified`; discovered values remain visible. Runtime admin output settings still apply. Without an explicit model override, increasing the global cap alone does not increase a model's reviewed output cap. No override sets `openbroker_limits_verified` to true.

Confirm higher limits from the actual serving operator or a separately authorized, funded boundary test. No paid boundary tests were performed as part of this change.

Previously saved admin settings take precedence over environment defaults for the global output cap. A saved 16,384 admin cap cannot raise the new reviewed per-model 4,096 limit. It can still constrain an explicit 32,768 model override, so check both server and saved admin policy when deliberately changing a deployment. Existing explicit model overrides are preserved and remain unverified; operators should review them against their actual provider configuration.

## Admission counting and evidence

The numeric context/output values are a **local policy informed by Gonka documentation and optionally tightened by separate proxy metadata**, not an OpenBroker account benchmark. OpenBroker currently does not publish numeric limits in its own docs. `/api/models` includes `openbroker_limits_verified: false` and `context_check: conservative_utf8_admission`.

Admission uses serialized UTF-8 size plus chat-envelope headroom, not an exact per-model tokenizer. It checks estimated input plus the requested per-choice output against the context policy. It can reject valid tokenized requests early, especially large Unicode/tool payloads; nothing is silently truncated. Exact full-window guarantees require pinned model tokenizers/chat templates and funded account testing.

Budget reservation separately includes **all requested completions**: estimated input + `n × max_tokens`. The maximum output refers to each choice, whereas billable output covers all choices. Admin per-wallet quota overrides and suspension are rechecked transactionally before reservation. Local model metadata reflects changed operator caps even while the upstream catalog is cached.

## Request bounds

Mirrors current Gonka Chat Completions safeguards where practical:

- Body: 10 MiB maximum.
- Messages: 2,048 maximum.
- `n`: 5 maximum.
- Stops: 16 strings, 256 bytes each.
- Default output: 4,096 tokens.
- Default maximum output: 4,096 tokens per choice, subject to effective per-model policy. Explicit operator configuration may change it within the 1,048,576 validation ceiling; that ceiling is not an upstream capability claim. Client examples follow the selected model's effective cap.
- `max_tokens` and `max_completion_tokens` are aliases and must agree if both are supplied.
- Maximum JSON nesting depth: 32.
- Live provider health is checked before dispatch; an explicitly unroutable/unavailable model returns 503 without spending holder allowance.
- Standard function tools/tool calls are passed through; Holdbyte does **not execute tools**.
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

## Provider cost and customer-price boundary

OpenBroker documents 10 ngonka per token **per attempt** and usually 10–25 effective ngonka per token due to retries/racing (about 15 typical), with additional epoch accounting possible. OpenBroker says its markup is 0%.

Configurable input/output rate-card fields are operator planning and reporting inputs. They do not charge a holder, create revenue or enable checkout. Before paid usage is offered, publish final prices, included amounts, payment settlement, taxes, expiration, refunds and dispute handling.

Holder allowance is funded separately in native GNK. Profitability analysis must include actual volume, GNK acquisition cost, provider retries and epoch adjustments, hosting, RPC, support, refunds, taxes and treasury operations. Do not make savings claims without matching the exact model revision, cache treatment, input/output mix and service limits.
