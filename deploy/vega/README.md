# Vega deployment

Vega builds Mealie directly from a clean repository checkout. No package registry,
GitHub Actions workflow, host Node installation, or host Python installation is
required; the multi-stage Dockerfile contains the complete build toolchain.

Production remains managed by:

- Compose project: `/home/vagabomd/services/mealie/compose.yaml`
- Persistent SQLite data: `/home/vagabomd/services/mealie/data`
- Carrie image override: `/home/vagabomd/services/mealie/compose.carrie.yaml`
- Deployment backups: `/home/vagabomd/services/mealie/deployment-backups`

The deployment script never stores application secrets in the repository. It
also leaves the base production Compose file unchanged.

## First checkout on Vega

The feature branch must first be pushed to `origin`. Then run:

```bash
ssh vega
cd /home/vagabomd/services
git clone https://github.com/asaxena76/mealie.git mealie-src
cd mealie-src
git switch feature/carrie-integration
git pull --ff-only origin feature/carrie-integration
```

For later deployments, update the existing clean checkout with the last two
commands. Deploy from an exact reviewed commit rather than from an uncommitted
working tree.

## Build and stage

```bash
cd /home/vagabomd/services/mealie-src
./deploy/vega/deploy.sh build
./deploy/vega/deploy.sh stage
./deploy/vega/deploy.sh status
```

`build` produces an immutable local image such as
`mealie:carrie-c467b1ddc`. `stage` briefly stops production while making a
consistent SQLite snapshot, immediately restarts production, then starts the
candidate against the snapshot on `127.0.0.1:9926`.

To inspect staging from another machine:

```bash
ssh -L 9926:127.0.0.1:9926 vega
```

Then visit `http://localhost:9926`. Confirm login, recipes, the meal planner,
household diners, cooking assignments, shared batches, and API-key access.

## Deploy

After staging has passed for the exact commit:

```bash
./deploy/vega/deploy.sh deploy --confirm
./deploy/vega/deploy.sh status
```

The script makes a fresh, quiesced copy of the production data, writes the
Compose override, starts the commit-tagged image, and waits for Docker health.
If health fails, it automatically restores both the previous data and previous
Compose override. The successful deployment output includes its exact rollback
command.

The normal downtime is the time needed to copy the small SQLite data directory,
run pending migrations, and pass the container health check.

## Cleanup and rollback

Remove the staging container after review:

```bash
./deploy/vega/deploy.sh clean-stage
```

To revert a successful deployment, use the exact backup directory printed by
the deploy command:

```bash
./deploy/vega/deploy.sh rollback \
  /home/vagabomd/services/mealie/deployment-backups/deploy-YYYYMMDDTHHMMSSZ \
  --confirm
```

Rollback does not delete the migrated database. It moves it into
`deployment-backups` before restoring the older copy, so it remains available
for diagnosis.

## Codex handoff prompt

The following is sufficient context for a Codex task running against Vega:

> In `/home/vagabomd/services/mealie-src`, update the clean
> `feature/carrie-integration` checkout with `git pull --ff-only`, read
> `deploy/vega/README.md`, then run the Vega deployment workflow. Build and
> stage first. Report the staging URL and migration/health result before running
> `deploy --confirm`. Do not modify or delete production data outside the
> deployment script. After deployment, verify container health and the
> `/api/app/about` endpoint.
