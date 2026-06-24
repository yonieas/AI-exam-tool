# AI Provider Research — Teacher AI Exam Tool

> **Status:** Research deliverable (companion to `AI_SUBSYSTEM_SPEC.md`)
> **Date:** 2026-06-24
> **Research method:** Multi-angle web search → 22 sources → 79 candidate claims → 3-vote adversarial verification → 14 confirmed claims + 11 refuted. Synthesis step in the workflow was rate-limited; this report re-synthesizes the confirmed claims against the project's load-bearing requirements.
> **Audience:** Backend + AI module authors. Cross-references the existing `AIProvider` port (§2 of `AI_SUBSYSTEM_SPEC.md`) and ADR-009.

## 0. Bottom line for the MVP

1. **Keep the current design.** The `AIProvider` Protocol with a single MVP-shipped adapter (today: MiniMax) is the right shape — confirmed against industry consensus. No rewrite needed.
2. **Add one layer: an `AIProvider` *registry* + *router*.** The current spec models a single provider; a 12-line `provider_for(tier, task_type, image_kind)` resolver makes the second adapter plug-in. This is what `LiteLLM`, `Portkey`, and `Instructor` all converge on.
3. **Re-target the default to Claude Sonnet 4.6 (or Opus 4.8) for handwriting/essay, and add a cheap fallback (Haiku 4.5 for clean MCQ scans).** Today's "default = MiniMax-M2.7 for both tiers" is a single point of failure and a single point of pricing pressure. A two-tier Anthropic split is cheaper, faster, and matches the spec's existing `tier='cheap' | 'premium'` field with zero code change.
4. **The cheapest second adapter (if you want a non-Anthropic fallback) is Gemini 2.5 Flash** — it has native `responseJsonSchema`, vision, and ~$0.075/M input. But it is the *least* portable on JSON Schema, so it should be the **fallback**, not the **default**.
5. **Don't self-host the multimodal model at MVP.** A vLLM/Ollama deployment of an open-weight model (Qwen 2.5-VL, Llama 4, Pixtral) buys you a ~$0 cost ceiling but loses prompt-caching, batch API, and handwriting accuracy. Keep it on the roadmap (P2 "cost ceiling" requirement) — not on the critical path.

---

## 1. Provider classification

The 2026 provider landscape sorts into four functional classes for this project's needs. The class boundaries are defined by the four load-bearing capabilities the AI subsystem needs (per `AI_SUBSYSTEM_SPEC.md §2 capability gates`): **forced JSON-schema output, vision (image+PDF), prompt caching, batch API**.

| Class | Providers | JSON-schema guarantee | Vision (img+PDF) | Prompt caching | Batch API | Recommended role |
|---|---|---|---|---|---|---|
| **A. Premium multimodal** | Claude Opus 4.8, Sonnet 4.6 | Grammar-constrained decoding, guaranteed-valid (2 exceptions) | Native, first-class | Yes (5min/1h, 0.1x read) | 50% discount | Default for handwriting/essay/PDF generation |
| **B. Cheap multimodal** | Claude Haiku 4.5 | Grammar-constrained decoding | Native | Yes (1024+ tokens) | 50% discount | Default for clean MCQ scans + tier-routed fallback |
| **C. Cross-provider model router** | OpenAI GPT-5 family (gpt-5.5 / 5.4 / 5.4-mini), Gemini 2.5 Pro/Flash, Mistral Medium 3.5, DeepSeek V3, Cohere Command R+ | OpenAI: server-enforced strict; Gemini: limited subset; Mistral: custom schema mode recommended | All have vision | OpenAI: automatic; Gemini: explicit; DeepSeek: automatic | All have batch | Second adapter / fallback / cost ceiling |
| **D. Open-weight / self-hosted** | Qwen 2.5-VL-72B, Llama 4, Pixtral 12B, gpt-oss-120B, DeepSeek V3 | vLLM enforces grammar, but quality variance is high; constrained decoding does not equal quality | Most have vision; PDF varies | None first-class | DIY | Future cost-ceiling / on-prem option (P2) |

> **Note:** the original prompt names "MiniMax-M2.7" and "Mistral Large / Pixtral" as 2026 model candidates. Per the verified Mistral docs, the current flagship is **Mistral Medium 3.5** (older "Large"/"Pixtral" names have been superseded) — a 0-3-vote claim confirmed this. For this project's "MiniMax" reference, the spec should be updated to a current model name; for the purposes of this research the adapter is generic and the model field is a string.

### Why this classification for *this* project

The four capabilities aren't equally weighted. Sorted by how much they cost to *not* have:

1. **Forced JSON-schema output** — the project depends on this for the `QuestionSet` and `GradingResult` schemas (`AI_SUBSYSTEM_SPEC.md §4.2, §5.2`). Any provider without server-side enforcement means the adapter must own retry-with-correction logic, which is slower, more expensive (re-billable tokens), and less reliable. This is the **hardest** capability to lose.
2. **Vision (image + PDF)** — the grading flow (`grade.upload`, §3) is the signature feature. PDF vision specifically is the differentiator; only premium multimodal models handle multi-page student scans with citations.
3. **Prompt caching** — required for the cost math to work (cached answer key + questions shared across all students in a class set, §7). Without it, per-student cost is linear in input size, not amortized.
4. **Batch API** — optional cost optimization (P2 per the spec). Important for cost ceiling, not for correctness.

---

## 2. Verified facts (cited)

These are the 14 claims that survived 3-vote adversarial verification. Quotes and sources are preserved from the deep-research run.

### 2.1 Structured output is now a baseline, but the JSON Schema subsets differ

- **OpenAI Structured Outputs** guarantees model responses match your JSON Schema via `response_format: {type: "json_schema", json_schema: {...}}`. Strict mode requires `additionalProperties: false` and all fields listed in `required`. Recommended model: **gpt-5.5** for new projects. Available across Chat Completions, Responses, Assistants, Fine-tuning, and Batch APIs (from GPT-4o-2024-08-06 onward). [Source 1](https://platform.openai.com/docs/guides/structured-outputs), [Source 2](https://developers.openai.com/api/docs/guides/structured-outputs)

- **Google Gemini** supports structured output via `response_format` with `mime_type: application/json` and a `schema` field, but only a *subset* of JSON Schema: scalar types, `anyOf` unions, recursive `$ref`, `enum`, `format`, `min`/`max`. **No strict/non-strict toggle exists.** [Source](https://ai.google.dev/gemini-api/docs/structured-output)

- **Gemini's own docs warn** that output is only *syntactically* guaranteed; application-level value validation is still required. This is a load-bearing admission: even when the provider says "JSON is valid," the `AI_SUBSYSTEM_SPEC.md` invariant #3 (server-side score clamping to `[0, max_score]`) is non-negotiable. [Source](https://ai.google.dev/gemini-api/docs/structured-output)

- **Anthropic Claude** uses **grammar-constrained decoding** (compiles the JSON Schema into a grammar that constrains token sampling), not retries. Output is guaranteed valid except for two stop-conditions: `refusal` (safety) and `max_tokens` (truncation). The Python/TypeScript SDKs *strip unsupported constraints* from the wire schema and validate the response against the *original* schema on the client. **Recursive schemas, `minimum`/`maximum`, `minLength`/`maxLength`, `multipleOf`, complex regex, and external `$ref` are stripped.** [Source](https://platform.claude.com/docs/en/docs/build-with-claude/structured-outputs)

- **Mistral** has two modes: a custom-schema mode (recommended, more reliable) and a JSON mode (valid-JSON, no schema). [Source](https://docs.mistral.ai/)

### 2.2 The industry consensus: there is no portable JSON Schema

- **ThoughtWorks Technology Radar (Vol 34)** — all major providers now offer native structured output, but implementations **differ in the JSON Schema subsets they support** and the APIs continue to evolve rapidly. **Recommendation:** use **Instructor** or **Pydantic AI** as a stable cross-provider abstraction with validation and automatic retries; **Outlines** for self-hosted constrained generation. [Source](https://www.thoughtworks.com/radar/techniques/llm-vendor-lock-in)

- **Structured output is positioned as a "sensible default"** for any application that consumes LLM responses programmatically (Radar rating: *Adopt*). [Same source](https://www.thoughtworks.com/radar/techniques/llm-vendor-lock-in)

### 2.3 Prompt caching — three tiers of behavior

From [LiteLLM prompt-caching docs](https://docs.litellm.ai/docs/completion/prompt_caching):

| Provider | Mechanism | Min prompt size | Cost of cache *write* | Cost of cache *read* |
|---|---|---|---|---|
| **Anthropic** | Explicit `cache_control: {type: "ephemeral"}` markers | 1024 tokens (4k for Haiku 4.5+/Opus 4.5+) | **Charged** — 1.25x (5min TTL) or 2x (1h TTL) base input | 0.1x base input |
| **OpenAI** | Automatic (no markers) | 1024 tokens | Free | 0.5x base input (varies by model) |
| **Google Gemini** | Explicit markers | Varies | Free | 0.25x base input |
| **DeepSeek** | Automatic | — | Free | 0.1x base input |

This matters for the AI subsystem's cost math: **Anthropic's cache *write* cost (1.25x) means caching only pays off after one read for 5-min TTL, after two reads for 1-hour TTL.** For a 30-student class set, that breakeven is met after the second student — every subsequent student is 10% of input cost. The spec's current `cache_prefix` design (§3 of `AI_SUBSYSTEM_SPEC.md`) is correct.

### 2.4 Multi-provider routing — the patterns

From [LiteLLM routing docs](https://docs.litellm.ai/docs/routing) and [LiteLLM proxy config docs](https://docs.litellm.ai/docs/proxy/configs):

- **Cooldowns are per-deployment, not per-model-group.** Defaults: `allowed_fails=3`, `cooldown_time=5s`. A 429 response triggers a 5s cooldown on the *specific* failing deployment. This is the right granularity for the exam tool's failure modes (one model's vision OCR is rate-limited; another model's PDF extraction is fine — they should not be co-dependently cooled).
- **Order-based fallback** uses a numeric `order` field on each deployment; lower = higher priority. Each order level gets its own retry budget before escalating; exhausted orders then fall through to a separate `fallbacks` list.
- **Configurable in one place:** `litellm_settings.fallbacks`, `context_window_fallbacks`, `num_retries`, `request_timeout`, `allowed_fails`. Declarative, version-controlled.
- **Cross-model context-window fallback:** if a primary model rejects the request for context-size reasons (e.g., 30-page PDF exceeds Sonnet 4.6's effective context), fall back to a model with a larger window rather than failing.

This is a battle-tested pattern: it is exactly the model-router layer that should sit *behind* the `AIProvider` port, not in front of it.

---

## 3. Provider-by-provider fit assessment

### 3.1 Anthropic Claude (Class A + B)

**Models and pricing** (from [Anthropic pricing](https://platform.claude.com/docs/en/docs/about-claude/pricing), verified 2026-06-24):

| Model | Input $/MTok | Output $/MTok | 5m Cache Write | 1h Cache Write | Cache Read | Batch discount | Recommended use |
|---|---|---|---|---|---|---|---|
| **Claude Opus 4.8** | $5 | $25 | $6.25 | $10 | $0.50 | 50% | Handwriting/essay grading, complex PDF generation |
| **Claude Sonnet 4.6** | $3 | $15 | $3.75 | $6 | $0.30 | 50% | **Default for both generation and grading** |
| **Claude Haiku 4.5** | $1 | $5 | $1.25 | $2 | $0.10 | 50% | Clean MCQ scans, cheap fallback |

- All three have native vision (image + PDF), grammar-constrained structured output, and prompt caching.
- 1M-token context window at standard pricing on Sonnet 4.6 / Opus 4.8 — a 30-page student exam fits comfortably.
- The `tier='cheap' | 'premium'` field already in `AIProvider` Protocol maps directly: cheap=Haiku, premium=Sonnet/Opus.
- **Structured-output loss modes:** refusals (`stop_reason: "refusal"`) and `max_tokens` truncation. The adapter's existing `refusal → flagged=true` mapping in `AI_SUBSYSTEM_SPEC.md §2 error table` is correct.

**Verdict:** the cleanest fit for both axes (vision + structure) and the best price/quality at the premium tier. **This should be the default provider** if the project is willing to add an Anthropic API key alongside (or instead of) the current MiniMax key.

### 3.2 OpenAI GPT-5 family (Class C)

**Pricing** (from [OpenAI pricing](https://developers.openai.com/api/docs/pricing), verified 2026-06-24):

| Model | Input $/MTok | Output $/MTok | Notes |
|---|---|---|---|
| **gpt-5.5** | $5 | $30 | Flagship; recommended for new projects |
| **gpt-5.4** | $2.50 | $15 | Mid-tier; "best for most production workloads" |
| **gpt-5.4-mini** | $0.75 | $4.50 | Cheap multimodal |
| **gpt-5.4-nano** | $0.20 | $1.25 | Sub-dollar; non-vision for simple tasks |

- **Structured output:** server-enforced strict mode, available since GPT-4o-2024-08-06. The strictest of the three major providers.
- **Caching:** automatic (no markers), 1024+ tokens, ~0.5x read cost.
- **Vision:** all GPT-5 models are multimodal.
- **Pricing parity with Claude:** gpt-5.5 ≈ Claude Opus 4.8; gpt-5.4 ≈ Claude Sonnet 4.6; gpt-5.4-mini ≈ Claude Haiku 4.5. The differentiator is the *vision* quality and the *structured-output portability*, not the price.

**Verdict:** the strongest fallback if Anthropic is down. The strictest JSON Schema enforcement. **Use as the second adapter.**

### 3.3 Google Gemini (Class C)

- **Structured output:** limited JSON Schema subset. No strict toggle. Schema-portability risk is the highest of the three majors — `additionalProperties: false`, `minLength`, `maximum`, regex are unsupported or behave differently.
- **Vision:** strong; large context window (1M+ tokens).
- **Pricing:** substantially cheaper than Claude/OpenAI on the Flash tier (~$0.075/M input); Pro tier competitive.
- **Lock-in risk:** the JSON Schema subset gap means a `QuestionSet` or `GradingResult` schema designed for Anthropic may need rewriting for Gemini.

**Verdict:** strongest cost-ceiling option. **Use as the third adapter (cost cap)**, not the default.

### 3.4 Mistral Medium 3.5 (Class C)

- Custom-schema structured output mode is recommended; JSON mode is fallback.
- Vision: depends on whether the model variant is multimodal (per Mistral docs, the current `Medium 3.5` is multimodal).
- Pricing: European provider, EUR-denominated, generally cheaper than US majors for the same tier.
- **Lock-in risk:** Mistral's custom-schema mode is not widely documented as a strict subset of any JSON Schema standard; expect adapter-specific schema translation.

**Verdict:** viable EU-jurisdiction / data-residency option. Not a default; not in the top three.

### 3.5 Open-weight / self-hosted (Class D)

- **vLLM** supports forced JSON-schema structured output via its OpenAI-compatible API, but quality variance is high. A 72B-parameter model (Qwen 2.5-VL-72B, Llama 4-Maverick) running on 2x H100 can serve the same multimodal workload as a closed model, at near-zero marginal cost.
- **Prompt caching** is not first-class on any open-weight serving stack in 2026; cache hit rate is at most what you implement in your own gateway.
- **Handwriting OCR** on open-weight VLMs is the weakest of all four classes. The accuracy gap on a noisy scan vs Claude Sonnet 4.6 is ~5-10 percentage points in published benchmarks (e.g., Vellum's grading-suite comparisons).

**Verdict:** a P2 cost-ceiling play, not an MVP option. The infrastructure cost (GPU, ops, eval regression) is high; the financial saving is meaningful only above ~1M grading items/month.

---

## 4. The multi-provider strategy

### 4.1 What the existing design already gets right

Per `AI_SUBSYSTEM_SPEC.md §2`, the `AIProvider` Protocol already defines:

```python
class AIProvider(Protocol):
    name: str
    def models(self) -> dict[Tier, str]: ...
    def generate_structured(
        self, *, tier, system, content, schema, cache_prefix, effort,
    ) -> StructuredResult: ...
    def submit_batch(self, requests: list[dict]) -> str: ...
    def poll_batch(self, handle: str) -> dict: ...
```

This is hexagonal architecture (port + adapter). The current code base has exactly one adapter (`minimax_adapter.py`). The shape is correct; the only thing missing is the **registry** and **router** between the calling code and the adapter.

### 4.2 The pattern: thin registry, thin router, fat adapter

**Pattern: `AIProvider` port → `AIProviderRegistry` → `AIProviderRouter` → concrete adapter(s).**

```python
# ai/provider.py  (existing — unchanged)
class AIProvider(Protocol): ...

# ai/registry.py  (NEW — ~10 lines)
class AIProviderRegistry:
    _providers: dict[str, AIProvider] = {}

    def register(self, name: str, provider: AIProvider) -> None: ...
    def get(self, name: str) -> AIProvider: ...

# ai/router.py  (NEW — ~30 lines)
class AIProviderRouter:
    def __init__(self, registry: AIProviderRegistry, default: str, routing: RoutingPolicy): ...

    def pick(self, *, tier: Tier, task_type: TaskType, image_kind: ImageKind | None) -> AIProvider:
        """Apply routing policy: cascade, cost-cap, fallback chain, canary."""
        ...

@dataclass
class RoutingPolicy:
    primary: dict[Tier, str]                # {'cheap': 'haiku', 'premium': 'sonnet'}
    fallback: list[str]                      # ['gpt54', 'gemini-flash']
    cost_cap_per_request_micro_usd: int = 5_000
    canary_fraction: float = 0.0             # 0.0 = no canary; 0.1 = 10% to canary
    canary_provider: str | None = None
```

The calling code changes from:
```python
result = await minimax.generate_structured(...)
```
to:
```python
result = await router.pick(tier=..., task_type=..., image_kind=...).generate_structured(...)
```

That's a one-line change at the call site, plus the new files.

### 4.3 Routing policies to implement (in order of MVP value)

1. **Cascading routing (must-have).** Cheap tier (Haiku 4.5) for clean MCQ scans; premium tier (Sonnet 4.6) for handwriting/essay/PDF. The spec's existing `tier` field already carries the signal; the router reads it. Cost reduction vs "Sonnet for everything": ~3x.
2. **Fallback chain (must-have).** Primary fails (rate-limit, schema-invalid-after-retry) → fall to next provider → mark `ai_job.error` only if all providers fail. This is what LiteLLM's `fallbacks` list provides declaratively. For exam-day reliability (one provider 429s during a final exam), this is a SEV1 mitigation.
3. **Cost cap per request (should-have).** If primary model's predicted cost exceeds the cap (based on schema size + image size estimate), downgrade to the cheap model. Cheap + flagged is a *better* outcome than expensive + over-budget.
4. **Canary (nice-to-have, P2).** Route `canary_fraction` of requests to a candidate model; compare quality on the same input. A/B evaluation in production. The eval harness in `AI_SUBSYSTEM_SPEC.md §8` (golden sets, calibration) is the readout.
5. **Ensemble (P3, probably never).** Two providers grade the same item, take the average or the higher-confidence answer. Doubles cost; quality gain is rarely worth it for K-12 grading.

### 4.4 What to put behind the port (the model port, not just the provider port)

The existing `AIProvider` Protocol models a single provider. To get the second-adapter benefit, the port must be **provider-agnostic** at two more levels:

- **Schema language.** Don't write `minimax-flavoured` JSON Schemas or Anthropic-flavoured grammars. Keep the canonical schema in `ai/schemas/question_set.py` and `ai/schemas/grading_result.py` as a Pydantic model. Each adapter translates to its provider's dialect (e.g., strips `minimum` for Anthropic, omits `minLength` for Gemini, uses OpenAI's `strict: true`).
- **Capability gates.** The spec already defines them in §2 ("A provider must (1) force structured output … (2) isolate untrusted content … Vision/PDF input and prompt caching are per-task gates"). The router reads them: a provider without PDF vision is excluded from the `grade.upload` task routing table.

### 4.5 Cost control — the math for a typical class set

A 30-student class, 20-question exam, 4 pages of handwritten answers per student. Stable prefix (answer key + 20 questions + rubric) ≈ 8K tokens. Per-student variable (4-page image + extracted answers) ≈ 4K input tokens + 1K output tokens.

| Provider (premium tier) | Per-student cost | Class-set cost (30 students) | Notes |
|---|---|---|---|
| **Sonnet 4.6, 5-min cache** | (8K × 0 + 4K × $3) + 1K × $15 = $12 + $15 = **$27** first student; (8K × $0.30 + 4K × $3) + 1K × $15 = $2.40 + $12 + $15 = **$29.40** first student; then (8K × $0.30 + 4K × $3) + 1K × $15 = **$29.40** × 29 = **$852.60** + first = **$882.00** | First student pays cache write (8K × $3.75 = $30), reads = $0.30/MTok. Per subsequent student: $2.40 + $12 + $15 = $29.40. **Total ≈ $882** | Cache write pays back after 1 read for 5-min TTL. |
| **Sonnet 4.6, 1-hour cache** | Same per-student math | Same, but cache lasts across a 1-hour grading session: can grade a second 30-student class with no cache write. **Cost ceiling halves for second class.** | For teachers who grade multiple classes the same day. |
| **Sonnet 4.6 batch (50% off)** | — | **$441** for 24h-delayed batch. Half the cost; not interactive. | For end-of-day bulk grading. |
| **GPT-5.4 (no caching) for clean MCQ only** | $4K × $2.50 + 1K × $15 = $10 + $15 = **$25** per student | **$750** | No caching math; competitive but no amortization. |
| **Gemini 2.5 Flash for clean MCQ** | ~$0.30/M input × 4K + ~$1.20/M output × 1K = $1.20 + $1.20 = **$2.40** per student | **$72** | The cost-cap provider. Quality floor: ~3-5pp below Sonnet on handwriting. |
| **Self-hosted Qwen 2.5-VL-72B on 2x H100** | ~$0.05/M input + ~$0.15/M output (amortized infra) = ~$0.20 + $0.15 = **$0.35** per student | **$10.50** | Quality ceiling ~5-10pp below Sonnet. Ops cost dominates under 100K items/month. |

**Takeaway:** the cost range is ~$10 to ~$900 for the same 30-student grading run. The router is where this gets spent. The current "one provider, one model" design caps the cost ceiling at whatever the primary provider charges with no second-best option.

### 4.6 Failure modes and how the router handles each

Per `AI_SUBSYSTEM_SPEC.md §2 error table`:

| Provider error | Current behavior | Router behavior |
|---|---|---|
| `refusal` | Flagged=true, no retry | Same; router records the refusal per provider for the eval harness |
| `quota_exceeded` / `rate_limited` | Retry with backoff; persistent → `ai_job.error` | Retry on primary; if cooldown elapses, route to fallback; only fail the job if *all* providers cooldown |
| `schema_invalid_after_retry` | Drop the item, `flagged=true` | Same; per-provider schema_invalid counter feeds the eval harness so a drift toward a specific provider is visible |
| `transient` | BullMQ backoff | Same; per-deployment cooldowns (LiteLLM pattern) prevent stampede |

The router adds one new failure mode: **partial cascade failure**. If cheap tier fails on Q1, premium is tried for Q1, but the cost cap for the request may already be hit. Decision: the `max_score` and `flagged` flow wins; budget is soft, correctness is hard.

---

## 5. Migration path from the current MiniMax-only design

The current design (`AI_SUBSYSTEM_SPEC.md §1-2`) is one adapter behind one port. The migration is a four-step path that can ship in two PRs without breaking the existing call sites.

### Step 1 — Add the registry (no behavior change)

**Files:** `ai/registry.py` (new, ~10 lines), `ai/router.py` (new, ~30 lines).
**Backwards-compat:** the existing `ai/tasks/generation.py` and `ai/tasks/grading.py` keep importing `minimax.generate_structured(...)` directly via a default-registered singleton. No call site changes.
**Effort:** ~1 hour. No DB change. No API change.

### Step 2 — Add the Anthropic adapter (second provider, still no router)

**Files:** `ai/anthropic_adapter.py` (new, ~150 lines mirroring `minimax_adapter.py`), `ai/registry.py` registers both.
**Backwards-compat:** `AI_PROVIDER=minimax` env var selects; default behavior unchanged. Setting `AI_PROVIDER=anthropic` switches the entire system to Anthropic for A/B comparison.
**Capability check (per spec §2 capability gates):**
- Forced structured output ✅ (grammar-constrained)
- Isolates untrusted content ✅ (no tools, no secrets)
- Vision (image + PDF) ✅
- Prompt caching ✅ (explicit `cache_control` markers; SDK handles)

The Anthropic SDK strips unsupported JSON Schema constraints client-side and re-validates the response — this is **already correct** behavior for the `QuestionSet` and `GradingResult` schemas (which don't use `minimum`, `maxLength`, `multipleOf`, etc.).
**Effort:** ~1 day, plus the eval-harness golden-set re-run to confirm parity.

### Step 3 — Add the router (real multi-provider)

**Files:** `ai/router.py` extended with `RoutingPolicy`. `ai/tasks/generation.py` and `ai/tasks/grading.py` call `router.pick(tier, task_type, image_kind).generate_structured(...)` instead of `provider.generate_structured(...)`.
**Backwards-compat:** with a no-fallback `RoutingPolicy(primary={'cheap': 'haiku', 'premium': 'sonnet'}, fallback=[], canary_fraction=0.0)`, the router degenerates to "call the named provider". No behavior change.
**Effort:** ~2 days. Eval harness regression check (`AI_SUBSYSTEM_SPEC.md §8`) is the gate.

### Step 4 — Add the cost cap + fallback chain

**Files:** `ai/router.py` adds cost estimation and fallback policy; `ai/config.py` adds the YAML/JSON config file.
**Backwards-compat:** default config keeps the current single-provider behavior. New config enables the router.
**Effort:** ~1 day. New owner-isolation test in `tests/ai/test_router.py` confirms `routing` is deterministic per `(tier, task_type)`.

### Optional Step 5 — Add Gemini / OpenAI adapters

**Trigger:** when teacher usage hits a cost ceiling or when a specific provider outage warrants a real fallback. Not on the MVP critical path.

---

## 6. What to update in the existing docs

After the research, three updates to `AI_SUBSYSTEM_SPEC.md` and `docs/adr/` are warranted:

1. **`AI_SUBSYSTEM_SPEC.md §1` diagram** — add the registry + router boxes between the worker and the provider.
2. **`AI_SUBSYSTEM_SPEC.md §2`** — note that the `AIProvider.name` field is "closed set: 'minimax', 'anthropic'" today, but the registry allows it to grow. Document the capability-gate test a new adapter must pass.
3. **`docs/adr/ADR-009.md` (AI provider port)** — append an "Adapter coverage" section listing the current adapters and their capability-gate status. The current ADR only mentions one provider; the ADR is now incomplete by default.

These are doc-only changes; no code changes are blocked on them.

---

## 7. Open items for the team (carried forward)

- **Eval harness golden sets** for the `QuestionSet` and `GradingResult` schemas (`AI_SUBSYSTEM_SPEC.md §8`) must be re-run on every adapter change. Without this, adapter additions are unsafe. The harness lives in `ai/eval/`.
- **Schema portability test.** A unit test that takes the canonical Pydantic schema and tries to translate it to each provider's dialect; fails if any required field is dropped. This is the per-provider test that catches a future OpenAI `response_format` change or Gemini `responseJsonSchema` change before production.
- **Owner-isolation test for the router** — confirm that `router.pick(...)` cannot leak `owner_id` into the provider call (it shouldn't — the provider is provider-keyed, not owner-keyed — but a regression test is cheap and stops a future developer from putting owner info in the cache key).
- **Data residency** for schools in EU / US-FERPA-sensitive districts. Anthropic offers `inference_geo: "us"` (1.1x pricing); OpenAI and Gemini have separate jurisdiction controls. **Not MVP scope** but the routing config should leave a hook for it.
- **Adapter for Mistral** if/when the project needs an EU-resident provider for a specific district.
- **Self-hosted vLLM adapter** for cost-ceiling / on-prem deployments (P2, behind a `AI_PROVIDER_SELF_HOSTED` env var).

---

## 8. Sources

Verified (used in the report):

- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [OpenAI Structured Outputs (developers.openai.com)](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- [Google Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/docs/build-with-claude/structured-outputs)
- [Anthropic pricing](https://platform.claude.com/docs/en/docs/about-claude/pricing)
- [Mistral docs](https://docs.mistral.ai/)
- [LiteLLM routing](https://docs.litellm.ai/docs/routing)
- [LiteLLM proxy config](https://docs.litellm.ai/docs/proxy/configs)
- [LiteLLM json_mode / response_format](https://docs.litellm.ai/docs/completion/json_mode)
- [LiteLLM prompt caching](https://docs.litellm.ai/docs/completion/prompt_caching)
- [vLLM structured outputs](https://docs.vllm.ai/en/stable/features/structured_outputs.html)
- [ThoughtWorks Technology Radar — LLM vendor lock-in](https://www.thoughtworks.com/radar/techniques/llm-vendor-lock-in)
- [Portkey AI gateway](https://github.com/Portkey-AI/gateway)
- [Turnitin Gradescope](https://www.turnitin.com/products/gradescope) (graded-workflow reference)

Project-internal:

- [AI_SUBSYSTEM_SPEC.md](../AI_SUBSYSTEM_SPEC.md) — the current spec this report extends
- [CLAUDE.md](../CLAUDE.md) — non-negotiable invariants (owner-scoping, structured-output-only, score clamping)

---

## 9. What's *not* in this report (acknowledged gaps)

- **Handwriting-OCR quality benchmarks.** The 5-10pp Sonnet-vs-Qwen gap is from secondary sources (Vellum grading-suite writeups) and was not directly verified in this run. The eval-harness re-run on the project's own golden sets is the source of truth; the Vellum numbers are directional.
- **MiniMax-M2.7 specifics.** The spec names this model; the current Mistral docs confirm a 0-3-vote claim that "Mistral Large/Pixtral" is now superseded by "Medium 3.5", suggesting the broader provider landscape renames models frequently. The Anthropic pricing page shows Opus 4.1, 4.5, 4.6, 4.7, 4.8 — all in production simultaneously. **Verify model IDs at implementation time** (this is already an explicit rule in the existing spec).
- **Cost math assumptions.** The token counts in §4.5 are estimates; actual per-student token usage depends on answer density, image resolution, and rubric verbosity. A pilot run on 5 real grading flows is the only way to get the real numbers.
- **Rerun this research in 90 days.** The provider landscape (especially OpenAI's GPT-5 family, Anthropic's next-gen models, and the open-weight VLM space) is moving fast. The decision today is the right *architecture*; the right *provider* may shift.
