#!/usr/bin/env node
/**
 * Deterministic PreToolUse guard for AntiGravity:
 *  - Denies non-interactive hang/policy traps in run_command (bare brew update,
 *    interactive brew --cask upgrade/reinstall, gh pr merge --admin, interactive sudo).
 *  - Rewrites run_checks outputMode "full" -> "compact" via `overwrite` when all
 *    subcommands are pass/fail build/test/lint/typecheck commands.
 *  - Strictly fail-open (<15ms, zero external deps).
 */
import fs from "node:fs";

function allow(extra) {
  const out = extra ? { decision: "allow", ...extra } : { decision: "allow" };
  process.stdout.write(JSON.stringify(out) + "\n");
}

function deny(reason) {
  process.stdout.write(JSON.stringify({ decision: "deny", reason }) + "\n");
}

function parseMaybeJson(val) {
  if (typeof val === "string") {
    try {
      return JSON.parse(val);
    } catch {
      return null;
    }
  }
  return val && typeof val === "object" ? val : null;
}

/**
 * Strip heredoc bodies, comments, and quoted literal arguments while preserving
 * `ENV_VAR=val` assignments so `echo "..."` / embedded scripts never false-positive.
 */
function sanitizeShellCommand(raw) {
  const lines = String(raw || "").split(/\r?\n/);
  const kept = [];
  let delim = null;
  let stripTabs = false;

  for (const line of lines) {
    if (delim !== null) {
      const check = stripTabs ? line.replace(/^\t+/, "") : line;
      if (check.trimEnd() === delim) {
        delim = null;
        stripTabs = false;
      }
      continue;
    }
    kept.push(line);
    // Match unquoted or delimiter-quoted heredoc operator outside simple single-quoted string
    const withoutQuotes = line.replace(/'[^']*'|"[^"\\]*(?:\\.[^"\\]*)*"/g, "");
    const hm = line.match(/<<(-?)\s*(['"]?)([A-Za-z_]\w*)\2(?:\s|$|;|&&|\|\|)/);
    if (hm && withoutQuotes.includes("<<")) {
      stripTabs = hm[1] === "-";
      delim = hm[3];
    }
  }

  let s = kept.join("\n");
  // Normalize VAR="val" / VAR='val' -> VAR=val before stripping standalone quoted args
  s = s.replace(/(^|[\s;&|()])([A-Za-z_]\w*)=(?:"([^"\n]*)"|'([^'\n]*)')/g, (_, p, k, d, sq) => {
    const v = d !== undefined ? d : (sq !== undefined ? sq : "");
    return `${p}${k}=${v}`;
  });
  // Strip single/double quoted string contents outside assignments
  s = s.replace(/'[^']*'|"[^"\\]*(?:\\.[^"\\]*)*"/g, '""');
  // Strip unquoted shell line comments
  s = s.replace(/(^|\s)#[^\n]*/g, "$1");
  return s;
}

function unwrapCommandSegment(seg) {
  let s = seg.trim().replace(/^\(+/, "").trim();
  let changed = true;
  while (changed) {
    changed = false;
    const mEnv = s.match(/^[A-Za-z_]\w*=\S*\s+(.*)$/);
    if (mEnv) {
      s = mEnv[1].trim();
      changed = true;
      continue;
    }
    const mCmd = s.match(/^(?:command(?:\s+-[pvV]+)*|nohup|time)\s+(.*)$/);
    if (mCmd) {
      s = mCmd[1].trim();
      changed = true;
      continue;
    }
    const mEnvCmd = s.match(/^env(?:\s+(?:-[iu0v]+|-u\s+\S+|--unset=\S+|[A-Za-z_]\w*=\S*))*\s+(.*)$/);
    if (mEnvCmd && s !== mEnvCmd[1]) {
      s = mEnvCmd[1].trim();
      changed = true;
    }
  }
  return s;
}

function isNonInteractiveSudo(cleanSeg) {
  // Tokenize options immediately following `sudo` before the target command
  const tokens = cleanSeg.trim().split(/\s+/).slice(1);
  const takesArg = new Set(["-u", "-g", "-p", "-C", "-h", "-r", "-t", "-U", "-D", "-R", "-T"]);
  let skipNext = false;
  for (const tok of tokens) {
    if (skipNext) {
      skipNext = false;
      continue;
    }
    if (tok === "--") break;
    if (!tok.startsWith("-")) break;
    if (tok === "--non-interactive") return true;
    if (!tok.startsWith("--")) {
      if (tok.includes("n")) return true;
      if (takesArg.has(tok)) skipNext = true;
    }
  }
  return false;
}

function inspectRunCommand(args) {
  const cmd = String(args?.CommandLine || "");
  if (!cmd.trim()) return allow();

  const sanitized = sanitizeShellCommand(cmd);
  const hasNoAutoUpdate = /(?:^|[\s;&|])HOMEBREW_NO_AUTO_UPDATE=1(?=$|[\s;&|])/.test(sanitized);
  const hasNoAsk = /(?:^|[\s;&|])(?:HOMEBREW_ASK=0|HOMEBREW_NO_ASK=1)(?=$|[\s;&|])/.test(sanitized);

  const segments = sanitized.split(/(?:&&|\|\||[;|\n])+/).filter((x) => x.trim());
  for (const seg of segments) {
    const cleanSeg = unwrapCommandSegment(seg);
    if (!cleanSeg) continue;

    if (/^brew\s+update(?:\s|$)/.test(cleanSeg)) {
      return deny(
        'Blocked bare `brew update` in non-interactive Agent terminal (slow/interactive risk). Refresh only the OPL tap via `git -C "$(brew --repository gaofeng21cn/one-person-lab)" pull --ff-only` and pass `HOMEBREW_NO_AUTO_UPDATE=1`.'
      );
    }

    if (/^brew\s+(?:upgrade|reinstall)\b/.test(cleanSeg) && /(?:^|\s)--cask(?:\s|=|$)/.test(cleanSeg)) {
      if (!(hasNoAutoUpdate && hasNoAsk)) {
        return deny(
          "Blocked `brew upgrade/reinstall --cask` without `HOMEBREW_NO_AUTO_UPDATE=1` and `HOMEBREW_ASK=0`/`HOMEBREW_NO_ASK=1` (may hang on `[y/n]` or `sudo` prompts). Download & verify the notarized DMG directly, or pass `HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_ASK=0` if sudo-free."
        );
      }
    }

    if (/^gh\s+pr\s+merge\b/.test(cleanSeg) && /(?:^|\s)--admin(?:\s|=|$)/.test(cleanSeg)) {
      return deny(
        "Blocked `gh pr merge --admin`: protected-branch owner merges must wait for CI (`mergeStateStatus: CLEAN`) and use `gh pr merge --merge --delete-branch` without `--admin`."
      );
    }

    if (/^sudo(?:\s|$)/.test(cleanSeg) && !isNonInteractiveSudo(cleanSeg)) {
      return deny(
        "Blocked interactive `sudo` in non-interactive Agent terminal (password prompt hangs). Use `sudo -n` for passwordless checks or ask the user to run it in their terminal."
      );
    }
  }

  return allow();
}

const INSPECT_STDOUT_RE =
  /\b(git\s+(status|diff|log|branch|rev-parse|show|remote)|ls|cat|head|tail|echo|printf|ps|lsof|gh|curl|jq|find|rg|grep|wc|stat|du|df|env|printenv|which|uname|sw_vers|lipo|codesign|spctl|shasum|plutil|defaults)\b|print\(|console\.log/;

const CHECK_CMD_RE =
  /^(?:(?:\S+\/)?(?:npm|pnpm|bun|yarn)\s+(?:run\s+)?(?:test|lint|typecheck|check|build|verify)(?::[\w:-]+)?|(?:\S+\/)?(?:npx|bunx)\s+(?:tsc|vitest|jest|eslint|biome)|(?:\S+\/)?(?:tsc|vitest|jest|pytest)|(?:\S+\/)?python3?\s+-m\s+(?:unittest|pytest|py_compile)|(?:\S+\/)?node\s+(?:--test|--check)|(?:\S+\/)?cargo\s+(?:test|check|clippy|build)|(?:\S+\/)?go\s+(?:test|vet|build)|(?:\S+\/)?swift\s+(?:test|build)|xcodebuild|(?:\S+\/)?(?:eslint|ruff|mypy|flake8|shellcheck)|(?:\.\/)?scripts\/(?:check|verify|test)[\w.-]*)(?:\s|$)/;

function stripCdAndEnv(raw) {
  let s = String(raw || "").trim();
  let changed = true;
  while (changed) {
    changed = false;
    const mCd = s.match(/^cd\s+[^&;]+(?:&&|;)\s*(.*)$/);
    if (mCd) {
      s = mCd[1].trim();
      changed = true;
      continue;
    }
    const mEnv = s.match(/^[A-Za-z_]\w*=\S*\s+(.*)$/);
    if (mEnv) {
      s = mEnv[1].trim();
      changed = true;
    }
  }
  return s;
}

function inspectRunChecks(args) {
  if (String(args?.outputMode || "") !== "full") {
    return allow();
  }
  const cmds = parseMaybeJson(args?.commands);
  if (!Array.isArray(cmds) || cmds.length < 1) {
    return allow();
  }

  for (const item of cmds) {
    const raw = typeof item === "string" ? item : String(item?.command || "");
    if (!raw.trim()) return allow();
    if (INSPECT_STDOUT_RE.test(raw)) return allow();
    const cleaned = stripCdAndEnv(raw);
    const parts = cleaned
      .split(/(?:&&|;)/)
      .map(stripCdAndEnv)
      .filter((p) => p && !/^cd(?:\s|$)/.test(p));
    if (parts.length === 0 || !parts.every((p) => CHECK_CMD_RE.test(p))) {
      return allow();
    }
  }

  return allow({
    reason:
      "Rewrote run_checks outputMode from 'full' to 'compact' for pass/fail build/test/typecheck commands to avoid 8.8KB truncation (failures still return full diagnostics).",
    overwrite: { outputMode: "compact" },
  });
}

function main() {
  try {
    const raw = fs.readFileSync(0, "utf8");
    if (!raw.trim()) return allow();
    const payload = JSON.parse(raw);
    const toolName = String(payload?.toolCall?.name || "");
    const args = parseMaybeJson(payload?.toolCall?.args) || {};

    if (toolName === "run_command") {
      return inspectRunCommand(args);
    }
    if (toolName === "mcp_agy-fast_fast_run_checks") {
      return inspectRunChecks(args);
    }
    return allow();
  } catch {
    return allow();
  }
}

main();
