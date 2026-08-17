# Takehome: Improving an AI Agent's Pass Rate on a Hardware Design Task

## Background

We build evaluation tasks for AI coding agents. An AI agent is given a hardware design problem — a specification and a skeleton of SystemVerilog code — and must write a complete, functionally correct implementation. The agent's solution is then graded by a hidden testbench that checks for bit-exact correctness. It is like an exam problem for a student: the student is given a problem statement and skeleton code and must write the complete solution, while the professor uses an automated grading system to grade it.

We also provide a golden solution that acts as a reference for the AI agent. This golden solution contains the correct implementation of the requirements described in the prompt and the specification, and it should always pass the testbench.

Your job in this takehome is to **create the golden solution, analyze why an AI agent is failing a specific task, then modify the specification to make the problem easier, thereby improving its pass rate**.

You are given a task where an AI agent (Claude Sonnet) achieves approximately **10% pass rate** across 20 independent attempts. Your goal is to modify the prompt/specification so that the agent achieves a pass rate **between 50% and 80%** (out of at least 10 runs).

---

## Section 0: Setup (~15 min)

**Tool Installations:**

Install the following if you don't already have them:

- [GitHub](https://github.com) account
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [Cursor IDE](https://cursor.com) (optional — any editor is fine)
- [Git](https://git-scm.com/downloads)
- [Python 3.10+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- [Icarus Verilog](https://steveicarus.github.io/iverilog/usage/installation.html) (`brew install icarus-verilog` on Mac, `apt install iverilog` on Linux)
- HUD account (you should have received an invite — let us know if not). Traces and job results live at [hud.ai](https://hud.ai).

**Windows users:** You will need WSL. Follow sections 3.1–3.5 of the [WSL Guide](https://docs.google.com/document/d/1LF0nSO5fTD7e_OC6GThE4AWRrnbPHl7Sz-8rnBxjEiM/edit?usp=sharing).

**Anthropic key:** You will also need an **Anthropic API key** (for calling the AI agent). Please check the email you received for your API key.

**GitHub setup:**

You will fork one repository (the problem-solving repo) and clone the framework repo. We recommend opening two terminals — one for the problem-solving repo and one for the framework.

**Problem-solving repo (use Terminal 1):** Forking gives you your own copy of the repo (with all branches included) where you can push your golden RTL and the spec modifications.

1. Fork the repo to your own GitHub account. Go to https://github.com/phinitylabs/takehome-mac-rne-sat and click **Fork**. Make sure the fork has **public** visibility. Remember to **uncheck** `Copy the mac_rne_sat_baseline branch only` when creating the fork.
2. Clone the repo you just forked:

```bash
git clone https://github.com/<your-github-username>/takehome-mac-rne-sat.git
cd takehome-mac-rne-sat
```

After cloning, check out each branch so they are available locally, then confirm you can see all three task branches:

```bash
git checkout mac_rne_sat_golden
git checkout mac_rne_sat_test
git checkout mac_rne_sat_baseline
git branch
```

You should see:

```
* mac_rne_sat_baseline
  mac_rne_sat_golden
  mac_rne_sat_test
```

**Framework repo (use Terminal 2):**

1. Clone the evaluation framework and install its dependencies:

```bash
git clone https://github.com/phinitylabs/verilog-coding-template.git
cd verilog-coding-template
uv sync
```

Set your API keys. Your HUD API key can be created on [hud.ai](https://hud.ai): go to your dashboard, click "Phinity Labs" in the bottom left, click **Settings** to open the project settings page, then go to the **API Keys** tab and create a new API key.

> **Note:** If you previously created an API key on the legacy HUD platform, that key will **not** work. Create a new key by following the steps above.

This framework uses **HUD v6**. Each problem runs in its own Docker image. The container serves a v6 control channel (`hud serve` on port 8765); the agent connects over SSH to edit files in the workspace. When the agent finishes, hidden tests grade the workspace via patch + pytest.

```bash
uv run hud set HUD_API_KEY=<your HUD key>
uv run hud set ANTHROPIC_API_KEY=<your Anthropic key from liaison>
```

---

## Section 1: Understanding the Task (~30 min) (Terminal 1)

The task is a signed 8×8 multiply-accumulate unit with a rounded, saturated readout port and a sticky overflow flag. The agent receives:

| File                     | Purpose                                              |
| ------------------------ | ---------------------------------------------------- |
| `prompt.txt`             | High-level instructions telling the agent what to do |
| `docs/spec.md`           | Detailed specification of the MAC unit's behavior    |
| `sources/mac_rne_sat.sv` | Empty module skeleton — the agent must fill this in  |

The agent does **not** see the test or the golden solution. It reads the prompt and spec, writes SystemVerilog code, and can run its own tests. After it finishes, the hidden testbench grades its implementation.

### Branch structure

The repo has three important branches:

| Branch                 | What's on it                                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `mac_rne_sat_baseline` | The starting point: empty skeleton + full spec. **This is what the agent sees.**                                   |
| `mac_rne_sat_test`     | Same as baseline, plus the hidden cocotb testbench (`tests/test_mac_rne_sat.py`). Used for grading.                |
| `mac_rne_sat_golden`   | Same as baseline; `sources/mac_rne_sat.sv` ships empty here — you implement your golden solution and push it to this branch. |

To look at the hidden test:

```bash
git checkout mac_rne_sat_test
cat tests/test_mac_rne_sat.py
```

To return to the baseline (what the agent starts with):

```bash
git checkout mac_rne_sat_baseline
```

Take time to read `docs/spec.md` and `sources/mac_rne_sat.sv`. Understand what the multiply-accumulate unit does.

---

## Section 2: Creating the Golden RTL (~1–2 hr)

Based on the specification file, create the golden RTL in `mac_rne_sat.sv` and push it to the `mac_rne_sat_golden` branch.

Make sure the RTL follows the specification file closely and fulfills every requirement.

To push your RTL, follow the steps below:

```bash
git switch mac_rne_sat_golden
git add sources/mac_rne_sat.sv
git commit -m "Update golden RTL"
git push origin mac_rne_sat_golden
```

---

## Section 3: Running Tests Locally (~10 min)

You can run the hidden testbench locally to verify that the golden solution passes and the baseline fails.

First, check out the test branch (which has the testbench):

```bash
git switch mac_rne_sat_test
```

Run the hidden testbench against the **baseline** code (this should fail — the skeleton ties its outputs low, so the testbench reports res/res_valid mismatches on the first cycles):

```bash
cd tests
uv run pytest test_mac_rne_sat.py --log-cli-level=INFO
```

You should see a failure. Now temporarily swap in the golden solution and re-run:

```bash
cd ..
git checkout origin/mac_rne_sat_golden -- sources/mac_rne_sat.sv
rm -rf sim_build __pycache__
cd tests
uv run pytest test_mac_rne_sat.py --log-cli-level=INFO
```

If your golden RTL is correct, this should pass. Restore the baseline skeleton before continuing:

```bash
cd ..
git checkout origin/mac_rne_sat_test -- sources/mac_rne_sat.sv
```

---

## Section 4: Analyzing Agent Behavior (~1 hr)

Here are the results of 20 runs of Claude Sonnet attempting this task with the current spec:

**[View the 20 runs here](https://www.hud.ai/jobs/5b12be34-8916-4930-b7ae-be3342506f91/traces)**

The agent achieves approximately **10% pass rate** — it solves the task correctly in very few of the 20 attempts.

Open one or more of the **failing** runs and carefully read through the agent's work. Pay attention to:

- What approach does the agent take?
- Where does it go wrong?
- What does it get right vs. wrong?
- Does it test its own code? What does it miss?
- Are there patterns across multiple failures?

Understanding *why* the agent fails is the key to this takehome. The agent is not randomly broken — there are specific, identifiable reasons it produces incorrect implementations. Your analysis of these reasons will directly inform how you modify the spec. We strongly recommend working backwards: look at the final implementation the agent created at the end of the trace and compare it to the golden solution. You can find the final implementation in HUD by scrolling to the bottom of the trace and looking through the code window in the final cell (on the left side of the transcript).

---

## Section 5: Modifying the Specification (~1–2 hr)

Your goal is to modify `docs/spec.md` (and/or `prompt.txt`) so that the agent's pass rate improves to **between 50% and 80%**.

The spec currently provides detailed guidance. You may modify any part of it — add detail, remove detail, restructure it, add hints, change wording — whatever you believe will help the agent produce correct implementations more often, based on your analysis in Section 4.

A few principles to keep in mind:

- The agent is an AI model, not a human engineer. What helps a human read a spec may not help (or may even hurt) an agent.
- The agent can look things up, write its own tests, and iterate. Consider what information it truly needs vs. what it can figure out on its own.
- Don't give the agent the solution directly (e.g., don't paste the golden code into the spec). The goal is to guide it, not hand it the answer.
- Ensure the final task given to the agent is unambiguous — all the information needed to implement it correctly should be present.
- If you modify a basic requirement, ensure the testbench is modified accordingly so that you don't test for a feature the specification never asked for.

Each time you make a change, test it by running on HUD (Section 6).

---

## Section 6: Running on HUD (~30 min) (Terminal 2)

Now switch to Terminal 2 to set up the framework.

**Register the problem.** Open `src/hud_controller/problems/basic.py` and append:

```python
PROBLEM_REGISTRY.append(
    ProblemSpec(
        id="mac_rne_sat",
        description="""Implement the module `mac_rne_sat` in sources/mac_rne_sat.sv according to
docs/spec.md.

Requirements:
- Synthesizable SystemVerilog, compatible with Icarus Verilog (-g2012).
- No SystemVerilog Assertions (SVA).
- Keep the module name, port names, directions, and widths exactly as in
  the provided skeleton.
- You may write and run your own tests, but grading is performed by a
  hidden testbench that checks cycle-exact behavior against docs/spec.md.

Deliverable: the completed sources/mac_rne_sat.sv. Do not modify any other
file.
""",
        difficulty="hard",
        base="mac_rne_sat_baseline",
        test="mac_rne_sat_test",
        golden="mac_rne_sat_golden",
        test_files=["tests/test_mac_rne_sat.py"],
    )
)
```

The branch names (`base`, `test`, `golden`) must exactly match the branches in your fork. Since forking preserves all branches, these already exist.

**Point the Dockerfile at your fork.** Open `Dockerfile` and find the `REPO_URL` line (near line 103):

```dockerfile
ARG REPO_URL=https://github.com/hud-evals/example-verilog-codebase.git
```

Change it to:

```dockerfile
ARG REPO_URL=https://github.com/<your-github-username>/takehome-mac-rne-sat.git
```

Since your fork is public, Docker can clone it without any authentication token.

### After each spec modification

**1. Update the branches.** From your forked repo (Terminal 1, `takehome-mac-rne-sat`), commit your spec change and push it to all three branches — baseline, test, and golden:

```bash
cd /path/to/takehome-mac-rne-sat
git checkout mac_rne_sat_baseline
# (make your spec edits to docs/spec.md)
git add docs/spec.md
git commit -m "modify spec"
git push origin mac_rne_sat_baseline

git checkout mac_rne_sat_test
git cherry-pick <commit-hash-from-above>
git push origin mac_rne_sat_test

git checkout mac_rne_sat_golden
git cherry-pick <commit-hash-from-above>
git push origin mac_rne_sat_golden
```

**2. Rebuild the Docker image.** Back in the framework repo (Terminal 2), first increment the cache-buster in the `Dockerfile` so Docker pulls fresh code from your fork (find the `ENV random=random6` line near `REPO_URL` and change the number, e.g. `random7`, `random8`, etc.). Then build:

```bash
cd /path/to/verilog-coding-template
uv run utils/imagectl3.py verilog_ -b --ids mac_rne_sat
```

**3. Validate** (confirm golden passes, baseline fails):

```bash
uv run utils/imagectl3.py verilog_ -v --ids mac_rne_sat
```

**4. Generate tasks and run** (10 independent attempts):

```bash
uv run utils/imagectl3.py verilog_ -j --ids mac_rne_sat
```

This writes `tasks.py` with one row per problem. Then run the local eval driver:

```bash
uv run python run_eval.py --ids mac_rne_sat --agent claude --model claude-sonnet-4-5 --max-steps 100 --group-size 10
```

`run_eval.py` starts a fresh Docker container per rollout, runs the agent, grades each attempt, and prints progress plus a job URL like `https://hud.ai/jobs/<job-id>`. Open that link to inspect individual rollouts.

Iterate until you achieve a 50–80% pass rate.

---

## Section 7: Submission

Once you have achieved a pass rate between 50% and 80%, email your liaison with:

1. **Your GitHub repo link** with the final specification and golden RTL.
2. **Your HUD results link** showing the pass rate.
3. **A written analysis** containing:

   **A. Root Cause Analysis.** Pick one failing run from the [original 20-run evaluation](https://www.hud.ai/jobs/5b12be34-8916-4930-b7ae-be3342506f91/traces). For that run, describe:
   - What the agent did wrong (the specific bug in its implementation).
   - Why it went wrong (what caused the agent to make that mistake).

   **B. Faulty Assumptions / Missed Insights.** What flawed reasoning, misconceptions, or missing domain knowledge led the agent to produce incorrect code? (e.g., did it misunderstand a concept in the spec? Did it use a Verilog pattern incorrectly? Did it skip a step?)

   **C. Prompt Modifications.** What did you change in the spec and why? Connect your changes to your analysis — explain how each modification addresses a specific failure mode you observed in the agent's behavior.

---

This takehome should take approximately **7–10 hours total**. The most important part is the analysis — we want to see that you can diagnose agent failures and reason about how to guide an AI model to produce correct hardware implementations.
