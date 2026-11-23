# Blockwise design board (Miro)

This folder builds our design-thinking board in Miro through Miro's REST API. The result is about 370 editable stickies, shapes, frames, connectors and 6 storyboard drawings.

| Frame | What's in it |
|---|---|
| 0 Start here | The whole story in one minute (problem, users, solution, proof, next) plus a clickable map of every frame |
| 1 Empathise · Personas | Arjun (contracting lead, primary user), Kavita (finance approver), Rahul (travel agent), Mei Lin (hotel revenue manager) |
| 2 Empathise · Empathy map | Says, Thinks, Does and Feels for Arjun, plus his pains and gains |
| 3 Empathise · Journey map | Arjun's season in 7 stages, with doing, thinking, a feeling curve, pain points and opportunities |
| 4 Define · Root-cause mind map | Why commitments go wrong, in 5 branches |
| 5 Define · Problem and HMW | Problem statement, point of view, 6 How Might We questions, success metrics, constraints and scope |
| 6 Ideate · Brainstorm | 35 ideas in 6 clusters, with dot votes; ✓ marks what Round 1 built |
| 7 Ideate · Prioritise | An impact × effort matrix |
| 8 Ideate · Product mind map | Blockwise's inputs, forecast, scenarios, optimiser, safeguards, outputs and proof |
| 9 Prototype · How it works | The pipeline, the 3 contract types and the safeguards |
| 10 Prototype · Storyboard | "The expo week" in 6 drawn panels |
| 11 Test · Evidence | Results table (the live site's current run: prepaid capped at 50% of last year's volume) and the limits we state up front |
| 12 Test · Roadmap | Now, Next and Later, plus open questions for TBO |
| 13 Strategy · SWOT | Strengths, Weaknesses, Opportunities and Threats (6 each, every number from the main README), plus 4 strategies that follow from them (TOWS) |

All content lives in [board.py](board.py) and all drawings in [drawings.py](drawings.py). To change something, edit it there and run the script again.

## Put it in Miro (about 5 minutes)

1. **Get a token.**
   1. Open Miro, then **Profile settings → Your apps → Create new app**. Any name will do.
   2. Under **Permissions**, tick `boards:read` and `boards:write`.
   3. Click **Install app and get OAuth token**, pick your team, and copy the token.
2. **Run the script** from the repo root (Python 3.9+, no installs needed):
   ```bash
   export MIRO_TOKEN='paste-token-here'
   python3 miro/board.py miro
   ```
   It takes 2 to 4 minutes, then prints the new board's link.
3. **Optional: use the hackathon's board.** If the organisers gave you a board, take the id from its URL (`miro.com/app/board/<ID>/`) and add `--board-id <ID>`. If that board already has content, add `--offset-x 6000` so ours lands to the right of it.

Keep the token private and don't commit it. You can revoke it under **Your apps** once you're done.

## Or use the Miro MCP (no token needed)

The board was built this way. Running `python3 miro/board.py canvas` writes one Canvas Composer SVG per frame to `miro/out/canvas/`. An agent connected to Miro's MCP (`https://mcp.miro.com`, set up in `.mcp.json`) sends each file with `canvas_create_from_svg`, then uploads `miro/storyboard/panel-*.png` into frame 10.

## Other commands

```bash
python3 miro/board.py miro --dry-run   # build every request without sending (miro/out/miro_requests.json)
python3 miro/board.py png              # re-render storyboard PNGs after editing drawings.py (needs Chrome)
```

Personas are composites, not real people, and the numbers in the storyboard are illustrative. The results numbers come from the main README.
