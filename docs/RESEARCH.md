# Research record

Sources reviewed **24 October 2026**. Model catalogs, provider configuration, prices, platform fees and launch availability can change. Keep the current conclusions in these focused documents instead of maintaining duplicate limit and pricing tables here.

| Topic | Current record |
| --- | --- |
| Model IDs, native versus deployed context, configurable output limits, request policy and provider pricing | [API policy](API-POLICY.md) |
| Pump.fun, StockLaunch, creator fees, treasury burns, proposed period locks and the AntSeed seller observation | [Token and treasury design](TOKEN-DESIGN.md) |
| Holdbyte identity and dated domain-availability quotes | [Brand](BRAND.md) |
| Keyless Gonka reads and the separation of treasury, broker credit and local allowance | [Gonka RPC](GONKA-RPC.md) |
| Remaining deployment and launch work | [Launch runbook](LAUNCH_RUNBOOK.md) |
| Automated checks and limits of fixture-based evidence | [Verification](VERIFICATION.md) |

## Source corrections retained

- OpenBroker's model catalog publishes current IDs without numeric context/output limits. A separate Gonka proxy's 16,384 output field does not verify OpenBroker's route.
- Gonka's pinned DevShard source calls 3,072 and 4,096 configurable defaults. The FAQ's description of 4,096 as a network ceiling is too broad. Holdbyte's local default is conservative; deliberate larger operator overrides remain labelled unverified.
- Native model configuration, Gonka deployment windows, local admission policy and measured account limits are separate kinds of evidence.
- The AntSeed seller is listed as OMA-AI. Its reported free usage is not paid settlement revenue or measured Holdbyte adoption.
- Manual business entries record operator assertions. They do not independently verify a fee receipt, swap, buyback or burn.
- The lock vault and treasury execution described in the design are proposals, not deployed contracts or enabled application features.

## Primary references

- [OpenBroker models](https://openbroker.gonka.gg/docs/models), [chat completions](https://openbroker.gonka.gg/docs/chat-completions), [pricing](https://openbroker.gonka.gg/docs/pricing), [usage](https://openbroker.gonka.gg/docs/usage), and [deposits](https://openbroker.gonka.gg/docs/deposits).
- [Pinned Gonka DevShard proxy documentation](https://github.com/gonka-ai/gonka/blob/b88062c9529389a61d4ba15b8b5603716a50909e/devshard/docs/proxy.md).
- Gonka [MiniMax](https://gonka.ai/docs/host/minimax-bootstrap/), [DeepSeek](https://gonka.ai/docs/host/deepseek-bootstrap/), and [GLM](https://gonka.ai/docs/host/glm-bootstrap/) deployment instructions.
- [Pump fees](https://pump.fun/docs/fees), [Tokenized Agent mechanism](https://pump.fun/docs/tokenized-agent-disclaimer), and [Solana burn instructions](https://solana.com/docs/tokens/basics/burn-tokens).
- [StockLaunch trust model](https://stocklaunch.world/docs/trust-model). Indexed official pages were available; direct retrieval returned HTTP 502 during this review.

The independent [AntSeedStats seller page](https://antseedstats.com/sellers/0x7b35030f77793159e86933e678b4e502c8fd9509) is a third-party observation source, not an official AntSeed settlement attestation. No paid inference, token launch, swap, bridge, burn, or treasury transaction was performed during this research.
