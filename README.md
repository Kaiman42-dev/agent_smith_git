*This project has been created as part of the 42 curriculum by dylekici and saaziev.*

# Agent Smith

## Description

Agent Smith is a **code agent**: an LLM that solves programming tasks by writing Python code,
running it in a sandbox, reading the result and trying again until the task is solved.

The agent follows a **Thought → Code → Observation** loop. Instead of calling tools through
JSON, the LLM writes Python that calls the tools directly
(`print(search_code(pattern="def add", file_pattern="*.py"))`), so it can keep variables
between steps, use loops and conditions, and chain several tools in one step.

It is evaluated on two benchmarks:

| Benchmark | Task | Expected output | Limits |
|---|---|---|---|
| **MBPP** | Write a small Python function | The function's code | 10 iterations, 6,000 input / 1,500 output tokens, 120 s |
| **SWE-bench Verified** | Fix a real bug in a real repository (sympy, django, xarray...) running in Docker | A `git diff` patch | 30 iterations, 300,000 input / 10,000 output tokens, 900 s |

Main features:

- our own agent loop (no agent framework such as smolagents, langgraph or crewai);
- a secure sandbox in a separate process: import allowlist, filesystem allowlist, no network,
  timeout, memory limit, restricted builtins;
- tools served by our own **MCP servers** (stdio and streamable HTTP), turned into Python
  functions inside the sandbox, with a manual generated from the server's schemas;
- support for several LLM providers (Gemini, Groq, OpenRouter), several API keys per
  provider with rotation, and automatic fallback to another provider;
- usage tracking for every step (tokens, latency, retries, requests).

## Instructions

### Requirements

- Python 3.10 and [uv](https://docs.astral.sh/uv/)
- Docker, for SWE-bench (the images are x86_64; on an Apple Silicon Mac they run under
  emulation, which the agent handles with `--platform linux/amd64`)
- Free-tier API keys for at least one provider in `models.json`

### Installation

```bash
uv sync
```

### API keys

Keys are never written in the code: they are read from environment variables, usually from a
`.env` file at the root of the repository (it is in `.gitignore`). Each provider can have
several keys, used in turn when one hits its rate limit:

```bash
GEMINI_API_KEY=...
GEMINI_API_KEY_1=...      # NAME, then NAME_1, NAME_2... (each name only once)
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
```

The variable name of each provider is set by `api_key_env` in `models.json`. A single variable
may also hold several keys separated by commas.

### Running the agents

The moulinette dumps a task, our agent solves it, the moulinette validates the solution:

```bash
# MBPP
cd moulinette && uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json && cd ..
uv run python -m agent_mbpp --task-file cache/mbpp_task.json --output cache/mbpp_solution.json
cd moulinette && uv run moulinette_eval validate mbpp ../cache/mbpp_task.json ../cache/mbpp_solution.json

# SWE-bench (Docker must be running)
cd moulinette && uv run moulinette_eval dump swebench --output ../cache/swebench_task.json && cd ..
uv run python -m agent_swebench --task-file cache/swebench_task.json --output cache/swebench_solution.json
cd moulinette && uv run moulinette_eval validate swebench ../cache/swebench_task.json ../cache/swebench_solution.json
```

Both agents accept the same options:

| Option | Default | Meaning |
|---|---|---|
| `--model-name` | `default_model` in `models.json` | Model to use |
| `--provider-url` | URL of `default_provider` | OpenAI-compatible API base URL |
| `--api-key-env` | guessed from the URL | Environment variable that holds the key |
| `--no-fallback` | off | Never switch provider (used for benchmarks: one model per run) |

`moulinette/quickstart.sh mbpp|swebench --student-path ..` runs the three steps in one command.
Before a SWE-bench session, `cd moulinette && uv run moulinette_eval warmup` downloads the
Docker images in advance, so the download does not eat into the agent's 900 seconds.

### Interactive sandbox

```bash
uv run sandbox                                                             # default limits
uv run sandbox sandbox_template.json                                       # custom limits
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json   # with MBPP tools
uv run sandbox --mcp-stdio "python mcp_tools_swebench.py" sandbox_template.json
uv run sandbox --mcp-server http://127.0.0.1:8000/mcp                      # MCP over HTTP
```

An MCP server can be started over HTTP with `python mcp_tools_swebench.py --http --port 8000`.
In the REPL, type Python; `exit` or Ctrl+D quits.

### Tests

```bash
uv run python -m pytest agent_algo agent_mbpp outils sandbox
```

The tests use fake LLM clients and fake sandboxes: no network and no API key needed.

## System architecture

```
 task.json ──▶ agent_mbpp/__main__.py  or  agent_swebench/__main__.py      (entry points)
                 │  read the task, start the MCP server (and Docker for SWE-bench),
                 │  run the agent, write solution.json, clean up
                 ▼
         agent_algo/agent.py ── Agent: the Thought → Code → Observation loop
                 │       ClientLLM: HTTP calls to the provider, key rotation, retries
                 │
   ┌─────────────┼──────────────────────────┐
   ▼             ▼                          ▼
 LLM API    Extraction_llm.py         sandbox/parent.py ──Pipe── sandbox/child.py
 (Gemini,   code blocks, XML,         runs the LLM's code in a     (restricted namespace)
 Groq,      JSON, ReAct → Python      separate process                   │ tool call
 OpenRouter)                                │                              ▼
                                            └── executes the tool ◀── tool proxy
                                                       │
                                     mcp_bridge.py + mcp_client.py (stdio or HTTP)
                                                       │
                                     mcp_tools_mbpp.py / mcp_tools_swebench.py (MCP servers)
                                                       │
                                     outils/: the tool code, confined to the repository
                                     (outils/testbed.py), commands run in the container
```

| Path | Role |
|---|---|
| `agent_algo/agent.py` | Agent loop (`Agent`), LLM client (`ClientLLM`), providers and fallback |
| `agent_algo/config.py` | Loads and validates `models.json` (providers, default model, benchmark models) |
| `agent_algo/metriques.py`, `agent_algo/rapport.py` | Per-run metrics and the Markdown tables of the benchmark report |
| `Extraction_llm.py` | Extracts the code from the LLM's answer |
| `sandbox/` | The sandbox: `parent.py` (process control), `child.py` (security), `protocol.py` (messages), `config.py` (limits), `cli.py` (REPL) |
| `mcp_client.py`, `mcp_bridge.py` | MCP client, and conversion of MCP tools into Python functions plus the LLM's manual |
| `mcp_tools_mbpp.py`, `mcp_tools_swebench.py` | Our MCP servers |
| `outils/` | Implementation of the SWE-bench tools |
| `models_public.py` | Pydantic models of the task inputs and of `solution.json` (identical to the moulinette's) |
| `models.json`, `sandbox_template.json` | Configuration of the models and of the sandbox |

## Agent loop

`Agent.agent_algo()` (`agent_algo/agent.py`) runs at most `max_tours` steps. Each step:

1. **Check the budget before spending it.** The agent stops cleanly if the time is up, if the
   output budget is used, or if the next call would exceed the input budget (each call resends
   the whole conversation, so the next call costs at least as much as the last one).
2. **Call the LLM** with the conversation. `max_tokens` is the remaining output budget, also
   capped per step for SWE-bench (`MAX_TOKENS_PAR_TOUR`), so a single runaway answer cannot use
   the whole task budget. If a provider fails (429, 5xx, timeout), `ClientLLM` retries, rotates
   to the next key, then the agent switches to the next provider in `models.json`.
3. **Extract the code.** `extraire_code()` tries, in order: Python code blocks, XML tool calls,
   JSON/Hermes tool calls, raw JSON, ReAct (`Action:` / `Action Input:`). Non-Python formats are
   converted into Python calls (`result = read_file(filepath=...)`), so the sandbox only ever
   sees Python. If the LLM starts inventing an `Observation:` after its code, the answer is cut
   there and the LLM is told why.
4. **Run the code** in the sandbox and add the output to the conversation as an `Observation`.
   The observation ends with the remaining step budget, and with a warning when few steps are
   left. For SWE-bench, only the last 4 observations stay complete; older ones keep their start
   and end only (the end of a test run holds the traceback), so the context stops growing at
   every step.
5. **Stop** when the code calls `final_answer(...)` (or the answer starts with `Final Answer:`).
   If the answer has no code and no final answer, the LLM gets a format reminder.

Every step is recorded as a `StepMetrics` (raw LLM output, code sent to the sandbox, sandbox
output, tokens, latency, retries, model, API URL) in `solution.json`. Extra data that the
`solution.json` format cannot hold (provider errors, fallbacks, intermediate metrics) goes in a
`solution.metrics.json` file next to it.

The system prompts are in `agent_mbpp/__main__.py` (short, because of the 6,000 input token
limit) and `agent_swebench/__main__.py` (method: reproduce with `run_tests()`, start from the
traceback, fix as soon as there is a hypothesis, submit as soon as the tests pass). Both include
an example loop and the tool manual generated from the MCP server.

## Sandbox design

The LLM's code runs in a **separate process** (`multiprocessing`, `spawn` start method) that
lives for the whole task, so variables are kept from one step to the next. The parent
(`sandbox/parent.py`) and the child (`sandbox/child.py`) talk through a `Pipe` with the
messages of `sandbox/protocol.py`. A separate process makes the timeout reliable: runaway code
is killed from outside, and the child is restarted (the LLM is told its variables were lost).

Security mechanisms, implemented with the standard library only:

| Constraint | How |
|---|---|
| Import allowlist | `__import__` is replaced. Only `authorized_imports` are allowed; `module.*` also allows submodules. The LLM receives filtered copies of the modules, not the real ones. |
| Filesystem allowlist | `open` is replaced. The path is resolved with `realpath` (handles `..` and symlinks) and must be inside `allowed_directories`. File descriptors are refused. |
| No network | `socket.socket` and `socket.create_connection` raise `PermissionError` in the child. |
| Timeout | The parent waits at most `max_execution_time_seconds` for the child, then kills and restarts it. |
| Memory limit | `resource.setrlimit(RLIMIT_AS)` in the child (Linux; macOS refuses it, and a warning is printed). |
| Restricted builtins | `eval`, `exec`, `compile`, `breakpoint`, `input` and `vars` are removed. `getattr`/`setattr`/`delattr` are wrapped, and the code is checked with `ast` before running: attributes starting with `_` are refused (except a small allowlist), because they are the usual way out (`__globals__`, `__subclasses__`...). |
| Output size | The captured `print` output is capped at 50,000 characters. |

The limits come from `SandboxConfig` (Pydantic, `sandbox/config.py`), loaded from a JSON file
such as `sandbox_template.json`.

Two kinds of functions live in the sandbox namespace:

- **MCP tool proxies**: they only send the call to the parent, which runs the real tool
  *outside* the sandbox (so tools are not subject to the sandbox restrictions or timeout);
- **`final_answer`**: provided by the sandbox itself, not by MCP, and always present. It stops
  the code and hands the answer to the agent loop.

`SystemExit` and `KeyboardInterrupt` raised by the LLM's code are not swallowed: they are sent
back to the parent and raised again, so the agent can stop cleanly and still write
`solution.json`.

## Tool implementation details

### MCP layer

- `mcp_client.py` picks the transport from the target: a URL means streamable HTTP, anything
  else is a command started over stdio. `SyncMcpClient` wraps the async client so the rest of
  the code stays synchronous.
- `mcp_bridge.py` turns each tool announced by the server into a Python function (positional
  arguments are mapped to the schema's parameter order) and generates the **manual** given to
  the LLM from the tool names, descriptions and parameter types. Connecting another MCP server
  changes the tools and the manual without any code change.
- Our servers expose tools, a resource with the task limits (`mbpp://limits`,
  `swebench://limits`) and a prompt (`solve_mbpp`, `solve_swebench`).

### MBPP tools (`mcp_tools_mbpp.py`)

- `run_tests(code, test_list)`: runs the candidate code followed by the assertions in a
  subprocess (10 s timeout) and returns `{"success": bool, "output": str}` as JSON.

### SWE-bench tools (`mcp_tools_swebench.py`, code in `outils/`)

| Tool | Behaviour |
|---|---|
| `read_file(filepath, start_line, end_line)` | Lines in the format `<line_number>: <line_content>` |
| `edit_file(filepath, old_str, new_str)` | Replaces an exact string that must appear exactly once; warns the LLM if a `.py` file no longer parses |
| `list_files(directory, pattern)` | Recursive glob, one absolute path per line |
| `search_code(pattern, file_pattern)` | grep-like search: `/absolute/path.py:<line> <content>` |
| `search_function_or_class_definition_in_code(name)` | Where a function or class is defined, same format |
| `find_references(name, filepath, line)` | Usages of a symbol, same format |
| `run_tests()` | Runs the task's `eval.sh`, returns the test part of the output (last 4,000 characters if too long, with a note) |
| `get_patch()` | `git -c core.fileMode=false diff` of the repository |
| `run_command(command, workdir)` | Shell command (120 s timeout), returns exit code, stdout and stderr |

The repository is located with the `TESTBED_PATH` environment variable (the moulinette sets it
when it tests the tools on their own). `outils/testbed.py` refuses any path outside it.
During a SWE-bench run, `agent_swebench` copies `/testbed` from the task's Docker image to a
folder on the host and mounts it on `/testbed` in the container: file tools work on the host
folder, commands and tests run in the container (`docker exec`), and both see the same files.
The container and the folder are always removed at the end, including when the moulinette
stops the agent with `SIGTERM` (signal handler).

## Benchmark results and analysis

The full model comparison (at least 5 models, 2 providers, 3 SWE-bench tasks), with provider
reliability, intermediate metrics and conclusions, is in
[BENCHMARK_REPORT.md](BENCHMARK_REPORT.md). The tables are generated from the `solution.json`
files with:

```bash
uv run python -m agent_algo.rapport <folders with solution.json files>
```

### Ablation: observation shortening and per-step token cap

Same task (`sympy__sympy-14711`), same model (`gemini-3.6-flash`), before and after keeping
only the last 4 observations complete, capping each step at 2,000 output tokens, and making the
SWE-bench prompt start from the traceback:

| | Before | After |
|---|---|---|
| Result | PASSED | PASSED |
| Iterations | 29 / 30 | 6 / 30 |
| Input tokens | 295,200 / 300,000 | 21,186 |
| Output tokens | 2,910 | 2,445 |
| Time | 433 s | 95 s |

Before the change, the agent read the files in small pieces for 24 steps, although the first
test run already pointed to the faulty line, and every read stayed in the context. A first
attempt that only asked the model to always write a `Thought:` failed: the model then invented
a whole conversation in one answer (about 9,500 output tokens in a single step), which is why
the per-step cap was added. This is a single run, and LLM outputs vary from one run to another.

The runs are in `cache/exam/` (before), `cache/exam_v2/` (failed attempt) and `cache/exam_v3/`
(after).

## Resources

- S. Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models* (2022):
  the Thought / Action / Observation loop.
- X. Wang et al., *Executable Code Actions Elicit Better LLM Agents* (CodeAct, 2024):
  why tools are called from Python code rather than JSON.
- C. E. Jimenez et al., *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?*
  (2023), and OpenAI's *SWE-bench Verified* (2024).
- J. Austin et al., *Program Synthesis with Large Language Models* (2021): the MBPP dataset.
- [Model Context Protocol](https://modelcontextprotocol.io/) specification and the
  [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
- [smolagents](https://huggingface.co/docs/smolagents) documentation, read as a reference for
  code agents (the library itself is not used).
- Python documentation: `multiprocessing`, `resource`, `ast`, `builtins`, `subprocess`.
- [uv](https://docs.astral.sh/uv/) and [Pydantic](https://docs.pydantic.dev/) documentation.

### How AI was used

- **Claude Code** was used to debug the SWE-bench runs: reading `solution.json` files to find
  why the agent wasted steps and tokens, then adding the observation shortening
  (`observations_completes`) and the per-step output cap (`max_tokens_par_tour`) with their
  tests (`agent_algo/test_memoire.py`, `agent_algo/test_limites.py`), and rewriting the method
  section of the SWE-bench prompt. The before/after runs above come from that work.
- **Claude Code** wrote the first draft of this README from the code; we reviewed it.
- *TODO: list the other parts of the project where AI was used (code, tests, debugging,
  documentation), and with which tool.*
