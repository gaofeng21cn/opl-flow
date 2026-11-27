# Record A Browser GIF

Use the repository's declared browser control and the bundled `encode_gif.py`
next to this guide. This route produces a local
artifact. Attaching it to a pull request requires a request to publish it.

## Record Truthful Evidence

Build and serve the exact target commit from a clean tree. Use isolated browser,
workspace, session, and application state unless the user explicitly requests
an existing session. Use the real configured API/model path for a real demo;
never substitute fixtures, mock transports, synthetic events, or test-only hooks
without saying so. Capture two to six semantic states from one run, wait for
concrete DOM predicates, and include the detail or trajectory needed to prove
tool calls, failures, or recovery. Do not capture secrets, personal data, or
unrelated tabs.

For continuous motion, record the demonstrated page with Playwright video when
the configured browser supports it. Match the recording size to the viewport,
keep the page's video handle and await context closure before saving the WebM.
Use ordered screenshots for discrete states or a browser without video.

Store the recording under the repository's ignored browser-artifact directory. Keep
dimensions and viewport stable. Require `ffmpeg` and `ffprobe`; report missing
media binaries instead of installing them implicitly. When Flow is installed,
use the Framework v2 Package repair/sync flow
(`opl pack ensure opl-flow --json` or `opl pack sync --json`) only when installation or repair
is authorized; the managed `ffmpeg` capability is ready only when both binaries
are callable.

## Encode And Verify

Run the encoder from this guide's directory. For example, trim a recording
and hold the final state, or assign display times to ordered screenshots.

```bash
python3 encode_gif.py demo.webm demo.gif --start 1 --end 5 --speed 2 --final-hold 1
python3 encode_gif.py frames demo.gif --durations 1,2,2
```

Set the frame rate, width, palette and byte limit to suit the destination. Read its JSON summary and inspect the encoded GIF itself, not just
the source frames. Confirm frame count, dimensions, duration, final-state hold,
byte size, and absence of sensitive content. Do not claim the GIF proves a
different commit, server, transport, or model than the one recorded.

## Publish Separately

When asked to attach the GIF, check the demonstrated commit against the live PR
head. On GitHub CLI with attachment support, append the file directly:

```bash
gh pr edit <number> --repo <owner/repo> --attach './demo.gif#Demonstrated workflow'
```

Read back the body, attachment, and head. A partial upload can update the PR
even when the command exits with an error. Reconcile the attachments before
retrying. Use the repository's documented asset route on hosts without native
attachment support.
