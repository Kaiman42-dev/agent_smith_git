# Moulinette helper notes

Moulinette-specific extras, see `exam_scripts_instructions.md` for the full
grading flow.

## Select exam tasks

From `moulinette/`:

```bash
cd moulinette
uv run moulinette_eval select swebench --count 3
uv run moulinette_eval select swebench --count 3 --seed 42 --output selection.json
```

## Run exam scripts

Same `exams/`, `student/`, `moulinette/` layout as `exam_scripts_instructions.md`:

```bash
./exams/exam_mbpp.sh --student-path ./student --moulinette-path ./moulinette --env-file .env
./exams/exam_swebench.sh --student-path ./student --moulinette-path ./moulinette --env-file .env
./exams/exam_sandbox.sh --student-path ./student --moulinette-path ./moulinette --env-file .env
```

Results go to `evaluations/(mbpp|swebench|sandbox)/$DATETIME/`.

## Exploring tasks directly (Fire CLIs)

```bash
cd moulinette

# MBPP
uv run moulinette_mbpp list_tasks
uv run moulinette_mbpp list_tasks --split test
uv run moulinette_mbpp get_task 42
uv run moulinette_mbpp evaluate_task_solution 42 "def similar_elements(a, b): return tuple(set(a) & set(b))"

# SWE-bench
uv run moulinette_swebench list_instances
uv run moulinette_swebench list_instances --repo_pattern "sympy"
uv run moulinette_swebench get_instance_info sympy__sympy-23534
uv run moulinette_swebench eval sympy__sympy-23534 --patch patch.diff
```

## Accessing gold patches

Use the `swebench` Python library directly, already a moulinette dependency.

## Adjusting difficulty

By default, the moulinette selects instances with difficulty `"<15 min fix"`.
Modify `moulinette/swebench/interact.py`:

```python
def list_instances(
    self,
    difficulty: Union[str, List[str], Difficulty, List[Difficulty]] = Difficulty.LESS_THAN_15_MIN,
    sort_by_patch_length: bool = False,
    limit: Optional[int] = 7,
) -> List[str]:
```

Available difficulties: `LESS_THAN_15_MIN`, `MIN_15_TO_1_HOUR`, `HOURS_1_TO_4`, `MORE_THAN_4_HOURS`.

## Changing limits

Edit `moulinette/models.py`:

```python
@classmethod
def mbpp_defaults(cls) -> "MetricsLimits":
    return cls(
        max_iterations=10,
        max_input_tokens=6_000,
        max_output_tokens=1_500,
        max_time_seconds=120.0,
    )
```

Keep this in sync with `subject/en.subject.tex`'s Hard Requirements table and
`tool/exams/exam_mbpp.sh`/`exam_swebench.sh`'s `*_TIME_LIMIT` constants if you
ever change these.
