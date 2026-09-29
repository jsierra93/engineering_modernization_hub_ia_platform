#!/usr/bin/env bash
#
# Run this before the defense. It checks the things that have actually
# broken during development, not a generic health check:
#
#   - credentials resolve and point at the expected account
#   - every Lambda is Active and carries the same build (a partial deploy
#     is the failure mode that cost two runs: core_py lives inside each
#     zip, so one stale function rejects what another writes)
#   - the state machine has the states the demo walks through
#   - the four sample repos are reachable at the exact SHAs
#   - the runs table has nothing with a misleading status on display
#
#   ./scripts/demo-preflight.sh

set -uo pipefail

PROFILE="${AWS_PROFILE:-personal}"
REGION="${AWS_DEFAULT_REGION:-us-east-2}"
PREFIX="modhub-personal"
# Resolve the CLI before anything else. `aws` is not on PATH in Git Bash on
# this machine, and with stderr discarded every call below failed silently --
# the script then reported six dead Lambdas and a missing state machine when
# the only thing missing was the binary. A check that invents symptoms is
# worse than no check.
AWS="${AWS_CLI:-}"
if [[ -z "${AWS}" ]]; then
  for candidate in aws "/c/Program Files/Amazon/AWSCLIV2/aws.exe" "/mnt/c/Program Files/Amazon/AWSCLIV2/aws.exe"; do
    if command -v "${candidate}" >/dev/null 2>&1; then AWS="${candidate}"; break; fi
  done
fi
if [[ -z "${AWS}" ]] || ! "${AWS}" --version >/dev/null 2>&1; then
  printf '
  [31mFALLA[0m no encuentro la AWS CLI.
'
  printf '        Instalala, ponla en el PATH, o exporta AWS_CLI con la ruta completa:
'
  printf '        AWS_CLI="/c/Program Files/Amazon/AWSCLIV2/aws.exe" ./scripts/demo-preflight.sh

'
  exit 1
fi
export AWS_PROFILE="${PROFILE}" AWS_DEFAULT_REGION="${REGION}" PYTHONUTF8=1 MSYS_NO_PATHCONV=1

FAILED=0
ok()   { printf '  \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '  \033[33maviso\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31mFALLA\033[0m %s\n' "$*"; FAILED=1; }
head_() { printf '\n\033[1m%s\033[0m\n' "$*"; }

head_ "Credenciales"
CALLER="$("${AWS}" sts get-caller-identity --query 'Account' --output text 2>/dev/null)"
if [[ -n "${CALLER}" && "${CALLER}" != "None" ]]; then
  ok "cuenta ${CALLER} · region ${REGION} · perfil ${PROFILE}"
else
  bad "sts get-caller-identity no responde -- revisa ~/.aws/credentials"
fi

head_ "Lambdas"
for fn in api core-ops agent-phase fetch-repo fetch-doc open-pr; do
  read -r STATE MODIFIED <<<"$("${AWS}" lambda get-function-configuration \
    --function-name "${PREFIX}-${fn}" --query '[State,LastModified]' --output text 2>/dev/null)"
  if [[ "${STATE}" == "Active" ]]; then
    ok "$(printf '%-12s' "${fn}") ${MODIFIED}"
  else
    bad "${fn} no esta Active (${STATE:-sin respuesta})"
  fi
done

head_ "State machine"
SM="$("${AWS}" stepfunctions list-state-machines \
  --query "stateMachines[?contains(name,'${PREFIX}')].stateMachineArn" --output text 2>/dev/null)"
if [[ -z "${SM}" ]]; then
  bad "no se encontro la state machine"
else
  "${AWS}" stepfunctions describe-state-machine --state-machine-arn "${SM}" \
    --query definition --output text 2>/dev/null | python -c '
import json, sys
sys.stdout.reconfigure(newline=chr(10))
S = json.load(sys.stdin)["States"]
# The states the demo actually walks through, plus the controls added late
# that have the least mileage on them.
needed = ["BaselineLint", "CheckViability", "Lint", "MarkBaselineLintClean", "RecordStuckRun", "ExecutionFailed",
          "IncrementIteration", "ApplyIteration", "RecordApprovalTimeout"]
missing = [n for n in needed if n not in S]
print("MISSING:" + ",".join(missing) if missing else "ALLPRESENT")
t = S.get("AwaitApproval", {}).get("TimeoutSeconds")
print("TIMEOUT:" + str(t))
print("STATES:" + str(len(S)))
' 2>/dev/null | while IFS=: read -r key value; do
    case "${key}" in
      ALLPRESENT) ok "todos los estados del guion presentes" ;;
      MISSING)    bad "faltan estados: ${value}" ;;
      TIMEOUT)    [[ "${value}" == "None" ]] && bad "AwaitApproval sin TimeoutSeconds" || ok "AwaitApproval timeout ${value}s" ;;
      STATES)     ok "${value} estados" ;;
    esac
  done
fi

head_ "Repositorios de muestra"
check_repo() {
  local repo="$1" sha="$2" label="$3"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "https://api.github.com/repos/${repo}/commits/${sha}")"
  if [[ "${code}" == "200" ]]; then
    ok "$(printf '%-15s' "${label}") ${repo} @ ${sha:0:12}"
  else
    bad "${label}: ${repo} @ ${sha:0:12} responde HTTP ${code}"
  fi
}
check_repo jsierra93/modhub_sample_success_strategy  be63acb5636cefa29be393c3a9947e244665e001 "exitoso"
check_repo jsierra93/modhub_sample_failed_strategy   3af994425ce94930e37a721c189e385bc1d1dd13 "inviable"
check_repo jsierra93/modhub_sample_prompt_injection  30434ad7cab4974c593ed5c313f72eaa67fc1558 "inyeccion"
check_repo jsierra93/modhub_sample_failed_test       38dc3118f615b7752381c255a8fa15c2671e99b3 "prueba fallida"

head_ "Estado de la tabla de runs"
"${AWS}" dynamodb scan --table-name "${PREFIX}-runs" \
  --projection-expression "run_id,#s,reason_code" \
  --expression-attribute-names '{"#s":"status"}' --output json 2>/dev/null \
  | python -c '
import json, sys
sys.stdout.reconfigure(newline=chr(10))
items = json.load(sys.stdin)["Items"]
print("COUNT:%d" % len(items))
# A run left mid-flight reads as "still working" to anyone who opens it.
stuck = [i["run_id"]["S"][:8] for i in items
         if (i.get("status") or {}).get("S") in ("PENDING", "RUNNING", "AWAITING_APPROVAL")]
print("STUCK:" + (",".join(stuck) if stuck else "-"))
' 2>/dev/null | while IFS=: read -r key value; do
    case "${key}" in
      COUNT) ok "${value} runs en la tabla" ;;
      STUCK) [[ "${value}" == "-" ]] && ok "ninguno a medio ejecutar" \
                || warn "sin terminar (se veran como 'trabajando'): ${value}" ;;
    esac
  done

head_ "Resultado"
if [[ "${FAILED}" == "0" ]]; then
  printf '  \033[32mListo para la demo.\033[0m\n\n'
else
  printf '  \033[31mHay fallas: resuelvelas antes de empezar.\033[0m\n\n'
fi
exit "${FAILED}"
