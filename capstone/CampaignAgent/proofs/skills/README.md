# Does a SKILL.md file actually change what the agent does?

Two runs. Same goal, same model (`gemini-2.5-flash`), same empty workspace with
`webcheck.js` sitting in it. The goal never mentions webcheck:

> Build index.html in the workspace: a small landing page for a developer tool
> called Arcturus. It needs a heading, two paragraphs of body copy, and a
> dark/light theme toggle that remembers the choice. Self-contained, no CDNs.

The only difference between the runs is the environment variable
`S17_SKILLS_DIR`, which lets the runtime discover `skills/web-pages/SKILL.md`.
No Python was imported, registered or changed between them.

## Result

| | nodes | seconds | commands run | shipped page |
| --- | ---: | ---: | --- | --- |
| without the skill | 2 | 31.5 | none | **FAIL** |
| with the skill | 16 | 420.0 | `node webcheck.js index.html` x3 | **PASS** |

Without the skill the agent wrote the file and answered. It ran nothing.

    $ node webcheck.js index_without_skill.html
    visible characters: 453 | clickable: 2 | responded: 1
    FAIL
      [file:// origin] JavaScript threw: Uncaught
        [Error: SecurityError: storage is unavailable on this origin]
    exit 1

That is the same defect as the original Arcturus landing page run: the theme
toggle reads `localStorage` at the top of the script, which throws on a
`file://` origin, and everything after it never executes. The page looks correct
in the browser it was written in and is broken in the one a person opens it
with. Nothing in the run reported a problem, because nothing in the run looked.

With the skill the agent ran the harness, read the failures, made eight edits
across three verification rounds, and converged:

    exit 1  ->  exit 1  ->  exit 0

    $ node webcheck.js index_with_skill.html
    visible characters: 464 | clickable: 2 | responded: 1
    PASS
    exit 0

## What this demonstrates

The behaviour that separates a shipped bug from a shipped page was added by
writing a markdown file. There is one class, `GenericSkill`, and it reads
`SKILL.md`. There is no `WebPageSkill`, and adding the next skill will not
create one.

It also shows the cost honestly. The skill turned a 31-second run into a
420-second one and 2 nodes into 16. Instructions are not free, which is why
`SkillManager` matches on declared keywords rather than injecting everything,
and why the injected block is capped.

## Files

- `summary.json` — both runs, machine readable
- `graph_without_skill.json`, `graph_with_skill.json` — the full checkpoints
- `index_without_skill.html`, `index_with_skill.html` — the two artifacts
- `injection_proof.txt` — the deterministic prompt-level check, no model required

## Reproducing it

```bash
export S17_WORKSPACE=/path/to/an/empty/git/repo      # with webcheck.js in it
export S17_SKILLS_DIR=$PWD/skills                    # omit for the control run
uv run sourcecode serve
```

`webcheck.js` needs `jsdom` on the path (`npm install jsdom`); without it the
harness exits 2 and says so rather than reporting a pass.

## The Bento deck

`attention_deck.bento.html` is not in this repository. It is 691 KB, and
almost all of that is Bento's own embedded player, which is their software
to distribute rather than ours. `jee_run/` carries the checkpoints, which is
the part that is evidence.
