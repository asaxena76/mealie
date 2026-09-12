#!/usr/bin/env bash

set -euo pipefail

MEALIE_DEPLOY_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEALIE_DEPLOY_REPO_ROOT="$(cd "${MEALIE_DEPLOY_SCRIPT_DIR}/../.." && pwd)"
MEALIE_DEPLOY_SERVICE_DIR="${MEALIE_VEGA_SERVICE_DIR:-/home/vagabomd/services/mealie}"
MEALIE_DEPLOY_COMPOSE_FILE="${MEALIE_DEPLOY_SERVICE_DIR}/compose.yaml"
MEALIE_DEPLOY_OVERRIDE_FILE="${MEALIE_DEPLOY_SERVICE_DIR}/compose.carrie.yaml"
MEALIE_DEPLOY_DATA_DIR="${MEALIE_DEPLOY_SERVICE_DIR}/data"
MEALIE_DEPLOY_BACKUP_ROOT="${MEALIE_DEPLOY_SERVICE_DIR}/deployment-backups"
MEALIE_DEPLOY_CONTAINER="${MEALIE_VEGA_CONTAINER:-mealie}"
MEALIE_DEPLOY_STAGE_CONTAINER="${MEALIE_VEGA_STAGE_CONTAINER:-mealie-carrie-stage}"
MEALIE_DEPLOY_STAGE_PORT="${MEALIE_VEGA_STAGE_PORT:-9926}"

cd "${MEALIE_DEPLOY_REPO_ROOT}"

MEALIE_DEPLOY_COMMIT="$(git rev-parse HEAD)"
MEALIE_DEPLOY_SHORT_COMMIT="$(git rev-parse --short=12 HEAD)"
MEALIE_DEPLOY_IMAGE="${MEALIE_VEGA_IMAGE:-mealie:carrie-${MEALIE_DEPLOY_SHORT_COMMIT}}"

usage() {
    cat <<EOF
Usage: $0 <command> [arguments]

Commands:
  build                     Build ${MEALIE_DEPLOY_IMAGE} from this checkout.
  stage                     Test the image on a snapshot at 127.0.0.1:${MEALIE_DEPLOY_STAGE_PORT}.
  clean-stage               Remove the temporary staging container.
  deploy --confirm          Back up production and deploy the staged image.
  rollback <backup> --confirm
                            Restore a deployment backup and its previous image.
  status                    Show production and staging status.

Optional environment overrides:
  MEALIE_VEGA_SERVICE_DIR, MEALIE_VEGA_CONTAINER,
  MEALIE_VEGA_STAGE_CONTAINER, MEALIE_VEGA_STAGE_PORT, MEALIE_VEGA_IMAGE
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command is missing: $1"
}

require_repo_clean() {
    [[ -z "$(git status --porcelain)" ]] || fail "The checkout has uncommitted or untracked files. Build from a clean commit."
}

require_service_layout() {
    [[ -f "${MEALIE_DEPLOY_COMPOSE_FILE}" ]] || fail "Missing ${MEALIE_DEPLOY_COMPOSE_FILE}"
    [[ -d "${MEALIE_DEPLOY_DATA_DIR}" ]] || fail "Missing ${MEALIE_DEPLOY_DATA_DIR}"
    [[ "${MEALIE_DEPLOY_SERVICE_DIR}" != "/" ]] || fail "Refusing to use / as the service directory"
}

validate_image_name() {
    [[ "${MEALIE_DEPLOY_IMAGE}" =~ ^[A-Za-z0-9._/:@-]+$ ]] || fail "Unsafe image name: ${MEALIE_DEPLOY_IMAGE}"
}

compose() {
    local -a mealie_deploy_compose_args=(-f "${MEALIE_DEPLOY_COMPOSE_FILE}")
    if [[ -f "${MEALIE_DEPLOY_OVERRIDE_FILE}" ]]; then
        mealie_deploy_compose_args+=(-f "${MEALIE_DEPLOY_OVERRIDE_FILE}")
    fi
    docker compose "${mealie_deploy_compose_args[@]}" "$@"
}

container_health() {
    docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null || echo "missing"
}

wait_for_health() {
    local mealie_deploy_target="$1"
    local mealie_deploy_attempt
    local mealie_deploy_status

    for mealie_deploy_attempt in $(seq 1 90); do
        mealie_deploy_status="$(container_health "${mealie_deploy_target}")"
        case "${mealie_deploy_status}" in
            healthy)
                return 0
                ;;
            unhealthy|exited|dead|missing)
                return 1
                ;;
        esac
        sleep 2
    done

    return 1
}

build_image() {
    require_repo_clean
    validate_image_name
    echo "Building ${MEALIE_DEPLOY_IMAGE} from ${MEALIE_DEPLOY_COMMIT}"
    docker build \
        --file docker/Dockerfile \
        --target production \
        --build-arg "COMMIT=${MEALIE_DEPLOY_COMMIT}" \
        --label "org.opencontainers.image.revision=${MEALIE_DEPLOY_COMMIT}" \
        --tag "${MEALIE_DEPLOY_IMAGE}" \
        .
}

require_image() {
    docker image inspect "${MEALIE_DEPLOY_IMAGE}" >/dev/null 2>&1 || fail "Build ${MEALIE_DEPLOY_IMAGE} first"
}

snapshot_data() {
    local mealie_deploy_kind="$1"
    local mealie_deploy_restart_after="${2:-true}"
    local mealie_deploy_timestamp
    local mealie_deploy_snapshot
    local mealie_deploy_was_running="false"

    mealie_deploy_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    mealie_deploy_snapshot="${MEALIE_DEPLOY_BACKUP_ROOT}/${mealie_deploy_kind}-${mealie_deploy_timestamp}"
    mkdir -p "${mealie_deploy_snapshot}/data"

    if [[ "$(docker inspect --format '{{.State.Running}}' "${MEALIE_DEPLOY_CONTAINER}" 2>/dev/null || true)" == "true" ]]; then
        mealie_deploy_was_running="true"
        compose stop "${MEALIE_DEPLOY_CONTAINER}" >&2
    fi

    if ! cp -a "${MEALIE_DEPLOY_DATA_DIR}/." "${mealie_deploy_snapshot}/data/"; then
        if [[ "${mealie_deploy_was_running}" == "true" ]]; then
            compose up -d --no-build "${MEALIE_DEPLOY_CONTAINER}" >&2
        fi
        fail "Could not create data snapshot ${mealie_deploy_snapshot}"
    fi

    if [[ "${mealie_deploy_was_running}" == "true" && "${mealie_deploy_restart_after}" == "true" ]]; then
        compose up -d --no-build "${MEALIE_DEPLOY_CONTAINER}" >&2
        wait_for_health "${MEALIE_DEPLOY_CONTAINER}" || fail "Production did not recover after the snapshot"
    fi

    printf '%s\n' "${mealie_deploy_snapshot}"
}

write_override() {
    local mealie_deploy_image="$1"
    local mealie_deploy_temp_override

    mealie_deploy_temp_override="$(mktemp "${MEALIE_DEPLOY_SERVICE_DIR}/.compose.carrie.XXXXXX")"
    cat >"${mealie_deploy_temp_override}" <<EOF
services:
  mealie:
    image: ${mealie_deploy_image}
    pull_policy: never
EOF
    mv "${mealie_deploy_temp_override}" "${MEALIE_DEPLOY_OVERRIDE_FILE}"
}

stage_image() {
    local mealie_deploy_snapshot
    local mealie_deploy_data_uid
    local mealie_deploy_data_gid
    local mealie_deploy_revision

    require_service_layout
    require_image
    if docker container inspect "${MEALIE_DEPLOY_STAGE_CONTAINER}" >/dev/null 2>&1; then
        fail "Staging container ${MEALIE_DEPLOY_STAGE_CONTAINER} already exists; run clean-stage first"
    fi

    mealie_deploy_snapshot="$(snapshot_data stage)"
    mealie_deploy_data_uid="$(stat -c '%u' "${MEALIE_DEPLOY_DATA_DIR}")"
    mealie_deploy_data_gid="$(stat -c '%g' "${MEALIE_DEPLOY_DATA_DIR}")"

    docker run -d \
        --name "${MEALIE_DEPLOY_STAGE_CONTAINER}" \
        --memory 2g \
        --publish "127.0.0.1:${MEALIE_DEPLOY_STAGE_PORT}:9000" \
        --volume "${mealie_deploy_snapshot}/data:/app/data" \
        --env "PUID=${mealie_deploy_data_uid}" \
        --env "PGID=${mealie_deploy_data_gid}" \
        --env DB_ENGINE=sqlite \
        --env ALLOW_SIGNUP=false \
        --env "BASE_URL=http://127.0.0.1:${MEALIE_DEPLOY_STAGE_PORT}" \
        "${MEALIE_DEPLOY_IMAGE}" >/dev/null

    if ! wait_for_health "${MEALIE_DEPLOY_STAGE_CONTAINER}"; then
        docker logs --tail 100 "${MEALIE_DEPLOY_STAGE_CONTAINER}" >&2 || true
        fail "Staging failed; production is still running unchanged"
    fi

    mealie_deploy_revision="$(docker exec "${MEALIE_DEPLOY_STAGE_CONTAINER}" python -c \
        'import sqlite3; connection = sqlite3.connect("/app/data/mealie.db"); print(connection.execute("select version_num from alembic_version").fetchone()[0])')"
    mkdir -p "${MEALIE_DEPLOY_BACKUP_ROOT}"
    printf '%s\n' "${mealie_deploy_snapshot}" >"${MEALIE_DEPLOY_BACKUP_ROOT}/.stage-ok-${MEALIE_DEPLOY_SHORT_COMMIT}"

    echo "Staging is healthy at http://127.0.0.1:${MEALIE_DEPLOY_STAGE_PORT}"
    echo "Database revision: ${mealie_deploy_revision}"
    echo "From another machine: ssh -L ${MEALIE_DEPLOY_STAGE_PORT}:127.0.0.1:${MEALIE_DEPLOY_STAGE_PORT} vega"
}

clean_stage() {
    if docker container inspect "${MEALIE_DEPLOY_STAGE_CONTAINER}" >/dev/null 2>&1; then
        docker rm -f "${MEALIE_DEPLOY_STAGE_CONTAINER}"
    else
        echo "No staging container exists"
    fi
}

restore_backup() {
    local mealie_deploy_backup="$1"
    local mealie_deploy_timestamp
    local mealie_deploy_displaced
    local mealie_deploy_previous_image

    [[ -d "${mealie_deploy_backup}/data" ]] || fail "Backup has no data directory: ${mealie_deploy_backup}"
    case "$(realpath "${mealie_deploy_backup}")" in
        "$(realpath "${MEALIE_DEPLOY_BACKUP_ROOT}")"/deploy-*) ;;
        *) fail "Rollback accepts only deploy-* directories inside ${MEALIE_DEPLOY_BACKUP_ROOT}" ;;
    esac

    compose stop "${MEALIE_DEPLOY_CONTAINER}" || true
    mealie_deploy_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    mealie_deploy_displaced="${MEALIE_DEPLOY_BACKUP_ROOT}/rollback-displaced-${mealie_deploy_timestamp}-data"
    mv "${MEALIE_DEPLOY_DATA_DIR}" "${mealie_deploy_displaced}"
    mkdir -p "${MEALIE_DEPLOY_DATA_DIR}"
    cp -a "${mealie_deploy_backup}/data/." "${MEALIE_DEPLOY_DATA_DIR}/"

    if [[ -f "${mealie_deploy_backup}/previous-override.yaml" ]]; then
        cp -a "${mealie_deploy_backup}/previous-override.yaml" "${MEALIE_DEPLOY_OVERRIDE_FILE}"
    elif [[ -f "${mealie_deploy_backup}/previous-image.txt" ]]; then
        mealie_deploy_previous_image="$(<"${mealie_deploy_backup}/previous-image.txt")"
        [[ "${mealie_deploy_previous_image}" =~ ^[A-Za-z0-9._/:@-]+$ ]] || \
            fail "Backup contains an unsafe previous image name"
        write_override "${mealie_deploy_previous_image}"
    elif [[ -f "${MEALIE_DEPLOY_OVERRIDE_FILE}" ]]; then
        mv "${MEALIE_DEPLOY_OVERRIDE_FILE}" "${mealie_deploy_backup}/rolled-back-override.yaml"
    fi

    compose up -d --no-build "${MEALIE_DEPLOY_CONTAINER}"
    wait_for_health "${MEALIE_DEPLOY_CONTAINER}" || fail "Rollback container is not healthy; inspect docker logs ${MEALIE_DEPLOY_CONTAINER}"
    echo "Rollback is healthy. Displaced data was preserved at ${mealie_deploy_displaced}"
}

deploy_image() {
    local mealie_deploy_confirmation="${1:-}"
    local mealie_deploy_backup
    local mealie_deploy_previous_image

    [[ "${mealie_deploy_confirmation}" == "--confirm" ]] || fail "Deployment requires: $0 deploy --confirm"
    require_service_layout
    require_image
    [[ -f "${MEALIE_DEPLOY_BACKUP_ROOT}/.stage-ok-${MEALIE_DEPLOY_SHORT_COMMIT}" ]] || \
        fail "Stage this exact commit before deployment: $0 stage"

    mealie_deploy_previous_image="$(docker inspect --format '{{.Config.Image}}' "${MEALIE_DEPLOY_CONTAINER}")"
    mealie_deploy_backup="$(snapshot_data deploy false)"
    printf '%s\n' "${mealie_deploy_previous_image}" >"${mealie_deploy_backup}/previous-image.txt"
    printf '%s\n' "${MEALIE_DEPLOY_IMAGE}" >"${mealie_deploy_backup}/deployed-image.txt"
    printf '%s\n' "${MEALIE_DEPLOY_COMMIT}" >"${mealie_deploy_backup}/deployed-commit.txt"
    if [[ -f "${MEALIE_DEPLOY_OVERRIDE_FILE}" ]]; then
        cp -a "${MEALIE_DEPLOY_OVERRIDE_FILE}" "${mealie_deploy_backup}/previous-override.yaml"
    fi

    compose stop "${MEALIE_DEPLOY_CONTAINER}" || true
    if ! write_override "${MEALIE_DEPLOY_IMAGE}"; then
        echo "Could not write the Compose override; restoring ${mealie_deploy_backup}" >&2
        restore_backup "${mealie_deploy_backup}"
        exit 1
    fi
    compose up -d --no-build "${MEALIE_DEPLOY_CONTAINER}"

    if ! wait_for_health "${MEALIE_DEPLOY_CONTAINER}"; then
        docker logs --tail 100 "${MEALIE_DEPLOY_CONTAINER}" >&2 || true
        echo "Deployment failed; restoring ${mealie_deploy_backup}" >&2
        restore_backup "${mealie_deploy_backup}"
        exit 1
    fi

    echo "Deployment is healthy: ${MEALIE_DEPLOY_IMAGE}"
    echo "Rollback backup: ${mealie_deploy_backup}"
    echo "Rollback command: $0 rollback ${mealie_deploy_backup} --confirm"
}

show_status() {
    local mealie_deploy_name
    for mealie_deploy_name in "${MEALIE_DEPLOY_CONTAINER}" "${MEALIE_DEPLOY_STAGE_CONTAINER}"; do
        if docker container inspect "${mealie_deploy_name}" >/dev/null 2>&1; then
            printf '%s | image=%s | status=%s\n' \
                "${mealie_deploy_name}" \
                "$(docker inspect --format '{{.Config.Image}}' "${mealie_deploy_name}")" \
                "$(container_health "${mealie_deploy_name}")"
        else
            echo "${mealie_deploy_name} | missing"
        fi
    done
}

require_command docker
require_command git

case "${1:-}" in
    build)
        build_image
        ;;
    stage)
        stage_image
        ;;
    clean-stage)
        clean_stage
        ;;
    deploy)
        deploy_image "${2:-}"
        ;;
    rollback)
        [[ -n "${2:-}" ]] || fail "Rollback requires a backup directory"
        [[ "${3:-}" == "--confirm" ]] || fail "Rollback requires --confirm"
        require_service_layout
        restore_backup "$2"
        ;;
    status)
        show_status
        ;;
    *)
        usage
        exit 2
        ;;
esac
