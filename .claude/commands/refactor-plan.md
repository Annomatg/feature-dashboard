Analyze this repository for code duplication using chunk-level similarity and create Feature MCP entries for the top refactoring candidates.

## Sequence of MCP Tool Calls

### Step 1 — Index and chunk

Call `index_repository` with the repository root, then call `chunk_repository` with the same root. Sequential — index must complete before chunking.

### Step 2 — Find production large functions

Call `find_large_functions`. Exclude any entry where the file basename starts with `test_`. These are the production functions with enough complexity to analyze.

Stop with "No large production functions found." if the filtered list is empty.

### Step 3 — Collect chunk maps

For each production function call `get_chunk_map` with `function_id`.

From each result, select chunks where `statement_range[0] != statement_range[1]` (multi-statement chunks only — skip single-statement atomic operations). If a function yields more than 5 qualifying chunks, take the 5 with the widest span (`statement_range[1] - statement_range[0]` descending).

### Step 4 — Cross-function similarity search

For each selected chunk call `analyze_chunks` with `chunk_id` and `top_k=5`.

Keep results where **both** conditions hold:
- `similarity_score >= 0.80`
- The matched chunk belongs to a **different function** than the query chunk (different `function_name` or different file)

### Step 5 — Deduplicate and rank

If pair (A→B) and (B→A) both appear, keep only the higher-scored entry. Sort by `similarity_score` descending. Take the top 10.

Stop with "No cross-function chunk similarity ≥ 0.80 found. No tasks created." if nothing remains.

### Step 6 — Create a Feature entry for each pair

| Field | Value |
|-------|-------|
| `category` | `"Refactoring"` |
| `name` | See template |
| `description` | See template |
| `steps` | See list |

**Name template** — infer a short pattern label from `normalized_code` or `refactoring_hint`:
```
<pattern_label> duplicated in <function_a> and <function_b>
```
Examples: `"state reset block duplicated in enable_autopilot and monitor_claude_process"`, `"spawn-and-monitor pattern duplicated in enable_autopilot and handle_autopilot_success"`

**Description template:**
```
Chunk similarity score: <score>

Pattern A: <function_a> in <relative_file_a> (statements <range_a>)
Pattern B: <function_b> in <relative_file_b> (statements <range_b>)

These chunks were identified as highly similar by chunk-level analysis.
Extracting the shared logic into a helper reduces duplication and improves maintainability.

Refactoring hint: <hint or "None">
```

**Steps list:**
1. `"Read both chunks in <function_a> and <function_b> to confirm the shared pattern"`
2. `"Extract the shared logic into a well-named helper function"`
3. `"Replace the chunk in <function_a> (<relative_file_a>) with a call to the helper"`
4. `"Replace the chunk in <function_b> (<relative_file_b>) with a call to the helper"`
5. `"Run the test suite to verify no regressions"`

## Rules

- MCP tool calls only — do not read, grep, or modify source files.
- Use paths relative to the repository root throughout.
- Skip intra-function pairs (same `function_name` and same file).
- Create features in score-descending order so highest-priority work appears first.
- Report final summary: functions analyzed, pairs found, features created, score range.

## Fallback: feature-mcp unavailable

Output pairs as a table:

| # | Score | Function A | File A | Function B | File B | Hint |
|---|-------|------------|--------|------------|--------|------|

Add: total pairs found, score range, note that no backlog entries were created.
