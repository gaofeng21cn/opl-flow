# Prototype a state model

Use one scenario that exposes the uncertain rule. For example, after a payment
is cancelled, what should happen when a delayed confirmation arrives?

For review by a domain expert, make a self-contained HTML file that opens
locally. Give actions and state fields the names reviewers already use. A
terminal harness is also appropriate when the question concerns CLI behavior
or needs the project's own runtime.

1. State the question in the demo. Start from a small, recognizable example.
2. Put the state transitions in a function or module independent of the
   controls. Use in-memory data and the same transitions for all interactions.
3. Show the available actions and current state after each step. Let reviewers
   try actions in different orders and reset to the initial state.
4. Include a replayable sequence for the disputed case. If an action should be
   refused, show its effect on both state and feedback.
5. Run the example and hand over the file or command with the sequence to try.
   Record which rule was confirmed or which question remains open before
   implementing the production behavior.

For a question about layout or interaction design, use [UI prototypes](UI.md).
