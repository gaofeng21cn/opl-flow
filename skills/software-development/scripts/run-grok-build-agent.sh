#!/bin/zsh
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run-grok-build-agent.sh start WORKTREE HANDOFF_FILE [-- GROK_OPTIONS...]
  run-grok-build-agent.sh resume WORKTREE SESSION_ID [-- SAME_GROK_OPTIONS...]

Run this helper from an exec session with a PTY (tty: true). Extra options are
passed to Grok and are intended for task-specific --deny rules. Start records
the launch settings in Git worktree metadata; resume reuses that receipt and
rejects conflicting settings.
EOF
}

fail() {
  print -u2 -- "error: $1"
  exit "${2:-64}"
}

reject_newlines() {
  local value
  for value in "$@"; do
    if [[ $value == *$'\n'* ]]; then
      fail "launch settings must not contain newlines"
    fi
  done
}

write_launch_receipt() {
  local receipt_tmp="${receipt_file}.tmp.$$"
  local value

  reject_newlines "$model" "$effort" "$permission_mode" "$worktree_root" "${extra_args[@]}"
  umask 077
  mkdir -p "${receipt_file:h}"
  {
    print -r -- "grok-build-agent-v1"
    print -r -- "$model"
    print -r -- "$effort"
    print -r -- "$permission_mode"
    print -r -- "$worktree_root"
    print -r -- "${#extra_args[@]}"
    for value in "${extra_args[@]}"; do
      print -r -- "$value"
    done
  } > "$receipt_tmp"
  mv -f "$receipt_tmp" "$receipt_file"
}

load_launch_receipt() {
  local -a receipt_lines saved_extra_args
  local saved_model saved_effort saved_permission saved_worktree saved_arg_count
  local i

  [[ -f $receipt_file ]] || fail "launch receipt not found for this worktree: $receipt_file" 66
  receipt_lines=("${(@f)$(<"$receipt_file")}")
  (( ${#receipt_lines[@]} >= 6 )) || fail "launch receipt is incomplete: $receipt_file" 65
  [[ ${receipt_lines[1]} == "grok-build-agent-v1" ]] || fail "unsupported launch receipt: $receipt_file" 65

  saved_model=${receipt_lines[2]}
  saved_effort=${receipt_lines[3]}
  saved_permission=${receipt_lines[4]}
  saved_worktree=${receipt_lines[5]}
  saved_arg_count=${receipt_lines[6]}
  [[ $saved_arg_count == <-> ]] || fail "invalid deny argument count in launch receipt" 65
  (( ${#receipt_lines[@]} == 6 + saved_arg_count )) || fail "launch receipt argument count does not match its contents" 65
  [[ $saved_worktree == "$worktree_root" ]] || fail "launch receipt belongs to a different worktree" 65

  saved_extra_args=("${receipt_lines[@]:6}")
  if (( model_override_set )) && [[ $requested_model != "$saved_model" ]]; then
    fail "GROK_BUILD_MODEL conflicts with the original launch receipt"
  fi
  if (( effort_override_set )) && [[ $requested_effort != "$saved_effort" ]]; then
    fail "GROK_BUILD_REASONING_EFFORT conflicts with the original launch receipt"
  fi
  if (( permission_override_set )) && [[ $requested_permission != "$saved_permission" ]]; then
    fail "GROK_BUILD_PERMISSION_MODE conflicts with the original launch receipt"
  fi

  if (( ${#extra_args[@]} > 0 )); then
    (( ${#extra_args[@]} == ${#saved_extra_args[@]} )) || fail "resume deny arguments differ from the original launch receipt"
    for (( i = 1; i <= ${#extra_args[@]}; i++ )); do
      [[ ${extra_args[i]} == "${saved_extra_args[i]}" ]] || fail "resume deny arguments differ from the original launch receipt"
    done
  else
    extra_args=("${saved_extra_args[@]}")
  fi

  model=$saved_model
  effort=$saved_effort
  permission_mode=$saved_permission
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  exit 0
fi

if (( $# < 3 )); then
  usage >&2
  exit 64
fi

mode=$1
worktree=$2
subject=$3
shift 3

if [[ ${1:-} == "--" ]]; then
  shift
fi

extra_args=()
while (( $# > 0 )); do
  if [[ $1 != "--deny" || $# -lt 2 ]]; then
    print -u2 -- "error: extra arguments must be repeated --deny RULE pairs"
    exit 64
  fi
  extra_args+=("$1" "$2")
  shift 2
done

if [[ $mode != "start" && $mode != "resume" ]]; then
  fail "mode must be start or resume"
fi

if [[ ! -t 0 || ! -t 1 ]]; then
  fail "Grok Build delivery requires a persistent PTY; run exec_command with tty: true"
fi

if ! command -v grok >/dev/null 2>&1; then
  fail "grok is not installed or not on PATH" 69
fi

worktree_root=$(git -C "$worktree" rev-parse --show-toplevel 2>/dev/null) || {
  fail "not a Git worktree: $worktree" 66
}
worktree_root=${worktree_root:A}
receipt_file=$(git -C "$worktree_root" rev-parse --git-path grok-build-agent-launch)
if [[ $receipt_file != /* ]]; then
  receipt_file="$worktree_root/$receipt_file"
fi
receipt_file=${receipt_file:A}

model_override_set=${+GROK_BUILD_MODEL}
effort_override_set=${+GROK_BUILD_REASONING_EFFORT}
permission_override_set=${+GROK_BUILD_PERMISSION_MODE}
requested_model=${GROK_BUILD_MODEL-}
requested_effort=${GROK_BUILD_REASONING_EFFORT-}
requested_permission=${GROK_BUILD_PERMISSION_MODE-}

model=${requested_model:-grok-4.6}
effort=${requested_effort:-high}
permission_mode=${requested_permission:-bypassPermissions}

if [[ $mode == "resume" ]]; then
  if [[ -f $receipt_file ]]; then
    load_launch_receipt
  elif [[ ${GROK_BUILD_ADOPT_LEGACY_RECEIPT:-0} == 1 ]]; then
    write_launch_receipt
    print -u2 -- "Adopted legacy Grok Build launch receipt: $receipt_file"
  else
    fail "launch receipt not found; for a pre-receipt session, recover its exact original settings and retry once with GROK_BUILD_ADOPT_LEGACY_RECEIPT=1" 66
  fi
fi

base_args=(
  --cwd "$worktree_root"
  --model "$model"
  --reasoning-effort "$effort"
  --permission-mode "$permission_mode"
  --no-plan
  --no-alt-screen
)

if [[ $mode == "start" ]]; then
  if [[ ! -f $subject ]]; then
    fail "handoff file does not exist: $subject" 66
  fi
  handoff_dir=$(cd "${subject:h}" && pwd -P)
  handoff_file="$handoff_dir/${subject:t}"
  write_launch_receipt
  print -u2 -- "Grok Build launch receipt: $receipt_file"
  initial_prompt="Read $handoff_file as the complete task contract. You are the sole implementation writer for this worktree, not a single-turn adviser. Use tools now and work to the stated terminal outcome. Keep Codex as the independent verifier."
  exec grok "${base_args[@]}" "${extra_args[@]}" "$initial_prompt"
fi

print -u2 -- "Reusing Grok Build launch receipt: $receipt_file"
exec grok "${base_args[@]}" "${extra_args[@]}" --resume "$subject"
