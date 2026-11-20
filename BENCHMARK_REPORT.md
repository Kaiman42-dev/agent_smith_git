# Benchmark report: model comparison on SWE-bench

This report compares LLMs driving our agent (`agent_swebench`) on SWE-bench tasks, under the
exam limits: 30 iterations, 300,000 input tokens, 10,000 output tokens, 900 s.
Every number below comes from a `solution.json` / `solution.metrics.json` file in `cache/`
(paths given in each section) and can be regenerated with:

```bash
uv run python -m agent_algo.rapport cache/bench_v5 cache/exam cache/exam_v5 cache/linux \
    cache/exam_20nov_gpt-oss-120b cache/exam_20nov_qwen3.8-27b
```

## 1. Setup

| | |
|---|---|
| Models | **20 tested** on the reference task, **5 retained** in `models.json` (section 6) |
| Providers | **3**: Groq, OpenRouter, Google Gemini (all free tier, OpenAI-compatible API) |
| Tasks | **7**: `sympy__sympy-14711`, `sympy__sympy-23534`, `sympy__sympy-18189`, `sympy__sympy-13480`, `django__django-11066`, `pydata__xarray-4629`, `scikit-learn__scikit-learn-13439` |
| Runs | 21 model-comparison runs (`gemma-4-31b-it` twice), 4 more tasks with one model, 6 ablation runs, 2 full exam runs (3 tasks each, section 5.3) |

**Why these providers.** The subject requires a free tier. Groq, OpenRouter and Gemini all expose
an OpenAI-compatible `/chat/completions` endpoint, so one client (`agent_algo/agent.py`) serves
all three. Using three providers instead of two spreads the free daily quotas: a 30-step
SWE-bench run can use 100k–300k input tokens, which exhausts a single free key quickly.

**Why these models.** The selection was done in three rounds, all on the reference task:

| Round | Models | Rule | Commit |
|---|---|---|---|
| Tested | 20 | the free models of the three providers available in November 2026 (after a first check on two MBPP tasks, `cache/bench/selection/`) | `16e44d9`, `2214297` |
| Kept | 10 | the models that submitted a patch | `2214297` |
| Retained | **5** | the 5 fastest of these 10 (wall time), listed in `benchmark_models` | `9b00696` |

The 5 retained models are `openai/gpt-oss-120b` and `qwen/qwen3.8-27b` (Groq),
`nvidia/nemotron-3.5-lightning:free`, `dots-studio/dots-3-note-preview:free` and
`nvidia/nemotron-3.5-super-vl:free` (OpenRouter). The full table of section 2.1 is kept to show
why the other 15 were left out.

**Why these tasks.** `sympy__sympy-14711` is our reference task: short issue, fast tests, so 20
models could be compared on it within the free quotas. The four other tasks come from four
different repositories (sympy, django, xarray, scikit-learn) and check that the agent is not
tuned to a single codebase.

**Limits of this setup (read before the tables).**
- The model comparison covers **one task** (`sympy__sympy-14711`). Only `gemini-3.6-flash` was
  run on all five tasks: free-tier quotas did not allow 20 models × 5 tasks.
- "Patch submitted" is the agent's own verdict (a non-empty patch given to `final_answer`).
  These runs were not all re-validated with `moulinette_eval validate`.
- Each configuration was run once. LLM outputs vary from one run to another, so a single pass or
  fail is an indication, not a success rate.

## 2. Results

### 2.1 Model comparison on `sympy__sympy-14711`

Same agent version for all rows (6 November 2026, `cache/bench_v5/`, and `cache/exam_v5/` for
`gemini-3.6-flash`), one run per model, `--no-fallback` (one model per run).

Rows in **bold** are the 5 retained models. Within each group, rows are sorted by wall time.

| Model | Provider | Patch submitted | Iterations | Input tokens | Output tokens | Wall time (s) |
|---|---|---|---|---|---|---|
| **`openai/gpt-oss-120b`** | groq | yes | 13 | 56,270 | 3,492 | **62** |
| **`qwen/qwen3.8-27b`** | groq | yes | 14 | 53,664 | **1,071** | 78 |
| **`nvidia/nemotron-3.5-lightning:free`** | openrouter | yes | 29 | 105,697 | 4,195 | 85 |
| **`dots-studio/dots-3-note-preview:free`** | openrouter | yes | 18 | 74,718 | 5,978 | 124 |
| **`nvidia/nemotron-3.5-super-vl:free`** | openrouter | yes | **11** | **34,719** | 3,599 | 128 |
| `gemini-3.5-flash-lite` | gemini | yes | 30 | 182,206 | 2,888 | 142 |
| `gemini-3.1-flash-lite` | gemini | yes | 26 | 156,801 | 6,722 | 240 |
| `gemini-3.5-flash` | gemini | yes | 30 | 181,174 | 3,771 | 288 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | openrouter | yes | 30 | 174,296 | 4,129 | 328 |
| `gemini-3.6-flash` | gemini | yes | 30 | 185,442 | 4,873 | 431 |
| `cohere/north-mini-code:free` | openrouter | no | 30 | 88,993 | 2,044 | 40 |
| `gemini-3-flash-preview` | gemini | no | 6 | 20,364 | 10,000 (limit) | 63 |
| `recursive/flint-v1.0:free` | openrouter | no | 29 | 232,122 | 10,000 (limit) | 136 |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | openrouter | no | 12 | 41,120 | 10,000 (limit) | 155 |
| `gemini-3.7-flash` | gemini | no | 0 | 0 | 0 | 217 |
| `openai/gpt-oss-20b` | groq | no | 30 | 191,772 | 1,260 | 243 |
| `xingchen-agi/xing4.0-29b-a4b:free` | openrouter | no (error) | 0 | 0 | 0 | 274 |
| `gemini-3.8-flash` | gemini | no | 0 | 0 | 0 | 275 |
| `gemma-4-26b-a4b-it` | gemini | no | 1 | 2,030 | 140 | 324 |
| `gemma-4-31b-it` (2 runs) | gemini | no | 0 | 0 | 0 | 145 / 238 |

10 of the 20 tested models submitted a patch. The failures fall into three groups:
- **Provider unavailable** (0 or 1 iteration): `gemini-3.7-flash`, `gemini-3.8-flash`,
  `gemma-4-31b-it` and `gemma-4-26b-a4b-it` only got timeouts and 500/503 errors. `xing4.0` got
  12 errors 429, then a response without a `choices` field, which stopped the run (see section 3).
- **Output budget exhausted**: `flint-v1.0`, `nemotron-3-nano-omni` and `gemini-3-flash-preview`
  reached the 10,000 output-token limit through long reasoning (nano-omni: 10,000 tokens in
  12 steps, flash-preview in 6).
- **Unparsable tool-call format**: `gpt-oss-20b` and `north-mini-code` used all 30 iterations
  answering in tool-call formats the agent cannot parse, so most steps ran no code (commit
  `2214297`).

### 2.2 One model on five tasks (`gemini-3.6-flash`)

| Task | Patch submitted | Iterations | Input tokens | Output tokens | Wall time (s) | Agent version |
|---|---|---|---|---|---|---|
| `django__django-11066` | yes | 8 | 32,735 | 379 | 280 | 1 Nov (`cache/exam/`) |
| `pydata__xarray-4629` | yes | 11 | 66,393 | 658 | 229 | 1 Nov (`cache/exam/`) |
| `sympy__sympy-23534` | yes | 13 | 72,350 | 2,125 | 223 | 30 Oct (`cache/linux/`) |
| `scikit-learn__scikit-learn-13439` | yes | 24 | 118,941 | 1,199 | 571 | 3 Nov (`cache/exam/`) |
| `sympy__sympy-14711` | yes | 30 | 185,442 | 4,873 | 431 | 6 Nov (`cache/exam_v5/`) |

5/5 patches submitted, all within the limits. These runs come from different agent versions
(before and after the changes of section 5), so they show that the agent works across
repositories, not a strict comparison between tasks.

## 3. Provider reliability

Computed over the 20 runs of `cache/bench_v5/` (`request_time_ms` of each step and
`provider_errors` of each `solution.metrics.json`).

| Provider | Runs | LLM steps | Avg response (ms) | Median response (ms) | Requests | Retries | Errors by type | Runs with no answer |
|---|---|---|---|---|---|---|---|---|
| Groq | 3 | 57 | **1,280** | **1,044** | 154 | 0 | 429: 97, 400: 36 | 0 / 3 |
| OpenRouter | 8 | 159 | 5,250 | 2,365 | 183 | 0 | 429: 22 | 1 / 8 |
| Gemini | 9 | 93 | 5,578 | 2,496 | 129 | 6 | timeout: 23, 500: 9, 503: 4 | 4 / 9 |

- **Groq is the fastest** (about 4× lower latency) **but the most rate-limited**: 97 errors 429
  in 3 runs (0.63 per request, against 0.12 for OpenRouter). Its free tier limits tokens per
  minute, and a SWE-bench context grows past 10k tokens per request. The 36 errors 400 are native
  tool calls refused by Groq for `gpt-oss`: the agent keeps the text the model generated and
  reads its code block, so they cost a request but not a step.
- **OpenRouter is the most available**: 22 errors 429 in 8 runs, and one model out of 8 never
  answered (`xing4.0`).
- **Gemini is the least available**: 4 of 9 runs got no usable answer (preview and Gemma models
  timing out), and its free tier allows 5 requests per minute (`"rpm": 5` in `models.json`).
  The models that do answer (`3.5-flash`, `3.6-flash`) are reliable.
- **Fixed since**: when a provider answered 200 without `choices` (`xing4.0`), the agent stopped
  the run with the error `'choices'`. Such a reply is now counted as a provider error
  (`"no choices"` in `provider_errors`) and retried like a timeout, then the agent falls back to
  the next provider (`ClientLLM.appel_llm` in `agent_algo/agent.py`).

## 4. Intermediary metrics

Computed by `agent_algo/metriques.py` from the steps of each `solution.json`:
- **First patch-file step**: first step whose `sandbox_input` reads or edits a file that appears
  in the final patch.
- **First failure drop**: first step where `run_tests()` reports fewer failing tests than in the
  first run (baseline).
- **Tests pass → final_answer**: number of steps between the first run with 0 failures and
  `final_answer`.

| Task / model | Iterations | First patch-file step | First failure drop | Tests pass (step) | Steps after tests pass |
|---|---|---|---|---|---|
| xarray-4629 / gemini-3.6-flash | 11 | 3 | 9 | 9 | 2 |
| sympy-23534 / gemini-3.6-flash | 13 | 3 | 10 | 10 | 3 |
| sklearn-13439 / gemini-3.6-flash | 24 | 4 | 18 | 18 | 6 |
| django-11066 / gemini-3.6-flash | 8 | 4 | - | - | - |
| sympy-14711 / qwen3.8-27b, gemini-3.1-flash-lite | 14, 26 | 1 | - | - | - |
| sympy-14711 / super-vl, dots-3-note, lightning, ultra, gemini-3.5-flash-lite | 11–30 | 2 | - | - | - |
| sympy-14711 / gemini-3.6-flash | 30 | 3 | - | - | - |
| sympy-14711 / gemini-3.5-flash | 30 | 4 | - | - | - |
| sympy-14711 / gpt-oss-120b | 13 | 7 | - | - | - |

`-` means the metric is not meaningful for that run: on `sympy-14711`, our failure counter reads
0 failures on the baseline run, so "failure drop" and "tests pass" cannot be measured; on
`django-11066`, no test run reported 0 failures before the submission.

**What this shows.**
- **Locating the bug is not the bottleneck.** In 13 of the 14 runs that submitted a patch, the
  agent touches the file of the final patch by step 4 (7 of them by step 2). We attribute this
  to the prompt rule "start from the last frame of the traceback".
- **Fixing is the bottleneck.** On the three tasks where it can be measured, the first
  improvement of the tests comes 6 to 14 steps after the right file was found (xarray 3 → 9,
  sympy-23534 3 → 10, sklearn 4 → 18).
- **Few steps are wasted after the tests pass** (2 to 6): the agent submits soon after. This was
  not the case before the change of 5.1, see below.

## 5. Ablations

Ablations 5.1 and 5.2 change the agent, with `gemini-3.6-flash` on `sympy__sympy-14711`, one run
per configuration. Ablation 5.3 changes the default model, under the exam conditions.

### 5.1 Observation shortening and per-step output cap

Change: keep only the last 4 observations in full (older ones shortened), cap each step at
2,000 output tokens, and make the prompt start from the traceback.

| | Before (`cache/exam/`) | Intermediate attempt (`cache/exam_v2/`) | After (`cache/exam_v3/`) |
|---|---|---|---|
| Patch submitted | yes | no | yes |
| Iterations | 29 / 30 | 3 | **6** |
| Input tokens | 295,200 / 300,000 | 6,846 | **21,186** |
| Output tokens | 2,910 | 10,000 (limit) | 2,445 |
| Largest single step (output tokens) | 592 | **9,567** | 889 |
| Wall time (s) | 433 | 125 | **95** |

Before, the agent read files in small pieces for 24 steps although the first test run already
pointed to the faulty line, and every read stayed in the context: 295k of the 300k input tokens.
The intermediate attempt only asked the model to always write a `Thought:`; the model then
wrote a whole imaginary conversation in one answer (9,567 output tokens in step 2), which is why
the per-step cap was added. With both changes: 14× fewer input tokens, 4.5× faster.

### 5.2 Fixed pause → per-key computed pause

Change: instead of waiting a fixed time before every request, the agent computes the wait from
each key's rate limit (`rpm` in `models.json`) and the time of that key's last request
(`ClientLLM` in `agent_algo/agent.py`).

| | Fixed 12 s pause (`cache/exam_v4/`) | Fixed 5 s pause (`cache/exam_v4_pause5/`) | Computed pause (`cache/exam_v5/`) |
|---|---|---|---|
| Patch submitted | no | no | yes |
| Iterations | 20 | 12 | 30 |
| Requests | 44 | 30 | 33 |
| Requests per iteration | 2.2 | 2.5 | **1.1** |
| Provider errors | 24 (429: 11, 503: 5, other: 8) | 18 (413: 6, 429: 4, other: 8) | **3** (503: 3) |
| Wall time (s) | 411 | 323 | 431 |

The computed pause removed the errors 429 (11 → 0) and halved the requests per iteration, which
saves the daily quota. The success of the last run is not caused by the pause: it depends on the
model's choices, and one run per configuration cannot separate the two.

### 5.3 Default model: `gpt-oss-120b` → `qwen3.8-27b`

Change: `default_model` in `models.json`. Both runs use `exams/exam_swebench.sh` exactly as in
the correction (3 tasks drawn at random from the pool of 6, default model with fallback, patches
validated by `moulinette_eval validate`), on 20 November 2026 with the same agent code. The
draws differ, except `sympy__sympy-18189`, which is in both.

| | `gpt-oss-120b` (`cache/exam_20nov_gpt-oss-120b/`) | `qwen3.8-27b` (`cache/exam_20nov_qwen3.8-27b/`) |
|---|---|---|
| Validated tasks | **1 / 3** | **3 / 3** |
| Tasks | django-11066 ✗, sympy-18189 ✗, sympy-13480 ✓ | sklearn-13439 ✓, sympy-18189 ✓, xarray-4629 ✓ |
| Iterations (avg) | 7.3 | 6.3 |
| Steps with no code | **13 / 22** | **0 / 19** |
| Input tokens (avg) | 24,588 | 21,590 |
| Output tokens (avg) | 559 | 336 |
| Wall time (avg, s) | 29 | 24 |
| Fallbacks | 0 | 0 |

Per task, on the shared one:

| `sympy__sympy-18189` | Result | Iterations | First patch-file step | Tests pass (step) |
|---|---|---|---|---|
| `gpt-oss-120b` | ✗ empty patch submitted at step 3 | 3 | - (never touched) | - |
| `qwen3.8-27b` | ✓ | 7 | 1 | 6 |

**Why `gpt-oss-120b` failed.** In both failed tasks it never edited a file, then called
`final_answer(get_patch())`: `get_patch()` answered `"No changes found."`, which was submitted as
the patch. On `django-11066`, 9 of its 13 steps produced no code at all (empty replies or prose
claiming the bug was fixed, mixed with errors 400 on refused tool calls). This behaviour appeared
after `reasoning_effort: low` was added for this model (commit `75ee9a3`): the `bench_v5` run that
solved `sympy-14711` predates it.

**What changed in the agent at the same time.** Before the `qwen` run, the agent was changed to
refuse a final answer while the repository has no changes (`refuser_patch_vide` in
`agent_swebench/__main__.py`, which checks the real `git diff` in the container, not the answer's
text). This refusal never triggered during the `qwen` run (`final_answer` was only called at the
last step of each task), so the 1/3 → 3/3 difference comes from the model, not from this change.

**Limits.** One run per model, and only one task in common. The other qwen results point the
same way: `sympy-14711` solved in `bench_v5` (14 steps) and `sympy-18189` solved again in a
separate run (8 steps).

## 6. Conclusions and model selection

**The 5 retained models** (`benchmark_models` in `models.json`):

| Model | Provider | Role | Data behind the choice |
|---|---|---|---|
| `qwen/qwen3.8-27b` | Groq | **default model** (since 5.3) | Fewest output tokens (1,071) on the reference task; 3/3 in the exam run, with no wasted step. |
| `openai/gpt-oss-120b` | Groq | benchmark (default until 5.3) | Fastest run on the reference task (62 s) and lowest latency (1.3 s per step), but 1/3 in the exam run: steps without code and empty patches. |
| `nvidia/nemotron-3.5-lightning:free` | OpenRouter | benchmark | Third fastest (85 s) despite 29 steps: short answers (2.3 s per step). |
| `dots-studio/dots-3-note-preview:free` | OpenRouter | benchmark | 18 steps, 124 s. |
| `nvidia/nemotron-3.5-super-vl:free` | OpenRouter | OpenRouter fallback | Fewest iterations (11) and input tokens; slow per step (9.7 s) but on the most available provider. |

Gemini is kept only as the last fallback (`fallback_model`: `gemini-3.5-flash-lite`, sixth
fastest at 142 s): it is the only provider tested on 5 tasks (`gemini-3.6-flash`, 5/5), but it
allows 5 requests per minute and times out often.

**Left out (15 models):**
- solved the task but slower than the 5 retained ones: `gemini-3.5-flash-lite`,
  `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `nemotron-3-ultra`, `gemini-3.6-flash`
  (142 to 431 s, 26 to 30 steps);
- never answered: `gemini-3.7/3.8-flash`, `gemma-4-26b/31b`, `xing4.0`;
- used up the 10k output tokens through long reasoning: `flint-v1.0`, `nemotron-3-nano-omni`,
  `gemini-3-flash-preview`;
- tool-call format the agent cannot parse: `gpt-oss-20b`, `north-mini-code`.

**Main lessons.**
1. With these limits, **context management matters more than the model**: the same model went
   from 295k to 21k input tokens with the changes of 5.1.
2. On a free tier, **provider availability matters as much as model quality**: 5 of the
   21 runs ended before the model could try anything.
3. **Fastest is not most reliable**: Groq answers 4× faster but returns 5× more errors 429 per
   request than OpenRouter, so the agent keeps a model from another provider ready to take over
   (`creer_clients_secours` in `agent_algo/agent.py`).
4. **One task is not enough to choose a model**: `gpt-oss-120b` was the best on the reference task
   and became the default, then scored 1/3 on the exam draw (5.3). Choosing on several tasks, under
   the exam conditions, is what changed the decision.

**Next steps.** Run the 5 selected models on at least 3 tasks with the same agent version,
validate every patch with `moulinette_eval validate`, and repeat each configuration to measure a
success rate instead of a single outcome.

## 7. Reproducibility

- Agent version: see the date of each run above. The `gpt-oss-120b` run of `bench_v5` predates
  `reasoning_effort: low` (commit `75ee9a3`); the two exam runs of 5.3 use the code of
  20 November 2026 (commit `409903a` plus the empty-patch check on the real `git diff`).
- Exam runs (5.3): `./exams/exam_swebench.sh --student-path . --moulinette-path ./moulinette
  --env-file .env` (on macOS, with GNU `coreutils` first in `PATH` for `mktemp --suffix`).
- One run: `uv run python -m agent_swebench --task-file <task.json> --output <solution.json>
  --model-name <model> --provider-url <url> --api-key-env <KEY> --no-fallback`
- Tables: `uv run python -m agent_algo.rapport <folders>` (reads `solution.json` and
  `solution.metrics.json`).
- Cost: $0 (free tiers only); the token counts are the cost proxy.
