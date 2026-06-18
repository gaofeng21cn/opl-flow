# External Practices Behind This Flow

Use this reference when explaining why the local workflow balances TDD and verification effort instead of applying one ritual everywhere.

## Absorbed Practices

- Risk-based testing: choose and prioritize test effort by risk, not by habit.
- Test pyramid / balanced portfolio: many small deterministic tests, fewer integration tests, very few end-to-end tests.
- Hermetic and small tests: prefer fast, reliable, diagnosable checks; large tests are more expensive and more likely to be flaky.
- Behavior over implementation: tests should protect observable contracts, not internal structure.
- Evidence-specific completion: green tests are not equivalent to live runtime, release, currentness, owner receipt, or end-to-end acceptance evidence.
- Test impact / affected checks: run the smallest check set that covers the changed surface before widening.
- Delete low-value tests: tests that are flaky, slow, duplicative, implementation-bound, or tied to retired compatibility surfaces are maintenance debt.

## Source Pointers

- Google Testing Blog, "Just Say No to More End-to-End Tests": supports the test pyramid and avoiding excessive broad tests.
  https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html
- Software Engineering at Google, testing chapters: supports small/medium/large test sizing, hermetic tests, and fast reliable feedback.
  https://abseil.io/resources/swe-book/html/ch11.html
  https://abseil.io/resources/swe-book/html/ch12.html
- Google Testing Blog, "Test Behavior, Not Implementation": supports behavior-focused tests.
  https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html
- Martin Fowler, "TestPyramid": supports a balanced testing portfolio.
  https://martinfowler.com/bliki/TestPyramid.html
- ISTQB Glossary, "risk-based testing": supports allocating test activities by risk.
  https://glossary.istqb.org/en_US/term/risk-based-testing
- Google Testing Blog, flaky test discussion: supports avoiding unnecessary large or flaky test surfaces.
  https://testing.googleblog.com/2017/04/where-do-our-flaky-tests-come-from.html
