---
name: record-browser-gif
description: Use when asked to record a browser or Web UI interaction as a GIF, or when a GUI pull request requires a truthful real-server demonstration; captures state-based frames, encodes them deterministically, and keeps recording separate from publication.
---

# Record A Browser GIF

Use the repository's declared browser control and the bundled encoder at
`skills/record-browser-gif/scripts/encode_gif.py`. This Skill produces a local
artifact; publishing it to a PR assets branch is a separate authorized action.

## Record Truthful Evidence

Build and serve the exact target commit from a clean tree. Use isolated browser,
workspace, session, and application state unless the user explicitly requests
an existing session. Use the real configured API/model path for a real demo;
never substitute fixtures, mock transports, synthetic events, or test-only hooks
without saying so. Capture two to six semantic states from one run, wait for
concrete DOM predicates, and include the detail or trajectory needed to prove
tool calls, failures, or recovery. Do not capture secrets, personal data, or
unrelated tabs.

Store frames under the repository's ignored browser-artifact directory. Keep
dimensions and viewport stable. Require `ffmpeg` and `ffprobe`; report missing
media binaries instead of installing them implicitly.

## Encode And Verify

Run the bundled encoder with explicit durations, frame rate, width, color, and
size limits. Read its JSON summary and inspect the encoded GIF itself, not just
the source frames. Confirm frame count, dimensions, duration, final-state hold,
byte size, and absence of sensitive content. Do not claim the GIF proves a
different commit, server, transport, or model than the one recorded.

## Publish Separately

Only when the user asks to attach the GIF to a PR, use a dedicated append-only
assets branch. Re-read the live PR head before and after editing its body,
verify the remote asset bytes and content type, and never commit media to the
product branch or force-push an assets branch.
