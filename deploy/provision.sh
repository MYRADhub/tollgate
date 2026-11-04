#!/usr/bin/env bash
# Provision Tollgate's Vultr infrastructure with the Vultr API v2:
# a Cloud Compute instance with Docker, a Managed PostgreSQL cluster, and an
# Object Storage subscription. Prints the values to put in deploy/.env.
#
# Usage: VULTR_API_KEY=... [REGION=atl] [PLAN=vc2-2c-4gb] [SSH_PUBKEY=~/.ssh/id_ed25519.pub] ./provision.sh
set -euo pipefail

: "${VULTR_API_KEY:?set VULTR_API_KEY}"
REGION="${REGION:-atl}"
PLAN="${PLAN:-vc2-2c-4gb}"
DB_PLAN="${DB_PLAN:-vultr-dbaas-hobbyist-cc-1-25-1}"
SSH_PUBKEY="${SSH_PUBKEY:-$HOME/.ssh/id_ed25519.pub}"
LABEL="${LABEL:-tollgate}"
API="https://api.vultr.com/v2"

v() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -fsS -X "$method" "$API$path" -H "Authorization: Bearer $VULTR_API_KEY" -H "Content-Type: application/json" -d "$body"
  else
    curl -fsS -X "$method" "$API$path" -H "Authorization: Bearer $VULTR_API_KEY"
  fi
}

command -v jq >/dev/null || { echo "jq is required"; exit 1; }

echo "== SSH key"
KEY_ID=$(v GET "/ssh-keys?per_page=100" | jq -r --arg n "$LABEL" '.ssh_keys[] | select(.name==$n) | .id' | head -1)
if [[ -z "$KEY_ID" ]]; then
  KEY_ID=$(v POST /ssh-keys "$(jq -n --arg n "$LABEL" --arg k "$(cat "$SSH_PUBKEY")" '{name:$n, ssh_key:$k}')" | jq -r .ssh_key.id)
fi
echo "   $KEY_ID"

echo "== Ubuntu 24.04 image"
OS_ID=$(v GET "/os?per_page=500" | jq -r '.os[] | select(.name|test("Ubuntu 24.04.*x64")) | .id' | head -1)
echo "   os_id $OS_ID"

USER_DATA=$(cat <<'CLOUD'
#cloud-config
package_update: true
packages: [ca-certificates, curl, git, ufw, fail2ban]
runcmd:
  - curl -fsSL https://get.docker.com | sh
  - ufw default deny incoming
  - ufw allow 22/tcp
  - ufw allow 80/tcp
  - ufw allow 443/tcp
  - ufw --force enable
  - systemctl enable --now docker fail2ban
CLOUD
)

echo "== Cloud Compute instance ($PLAN in $REGION)"
INSTANCE=$(v GET "/instances?label=$LABEL" | jq -r '.instances[0].id // empty')
if [[ -z "$INSTANCE" ]]; then
  INSTANCE=$(v POST /instances "$(jq -n --arg r "$REGION" --arg p "$PLAN" --argjson os "$OS_ID" --arg l "$LABEL" --arg k "$KEY_ID" --arg u "$(printf '%s' "$USER_DATA" | base64 | tr -d '\n')" \
    '{region:$r, plan:$p, os_id:$os, label:$l, hostname:$l, sshkey_id:[$k], user_data:$u, backups:"disabled", enable_ipv6:true}')" | jq -r .instance.id)
fi
echo "   $INSTANCE"

echo "== Managed PostgreSQL"
DB=$(v GET "/databases?label=$LABEL-db" | jq -r '.databases[0].id // empty')
if [[ -z "$DB" ]]; then
  DB=$(v POST /databases "$(jq -n --arg r "$REGION" --arg p "$DB_PLAN" --arg l "$LABEL-db" '{database_engine:"pg", database_engine_version:"16", region:$r, plan:$p, label:$l}')" | jq -r .database.id)
fi
echo "   $DB"

echo "== Object Storage"
OBJ=$(v GET "/object-storage?per_page=100" | jq -r --arg l "$LABEL-files" '.object_storages[] | select(.label==$l) | .id' | head -1)
if [[ -z "$OBJ" ]]; then
  CLUSTER=$(v GET /object-storage/clusters | jq -r --arg r "$REGION" '([.clusters[] | select(.region==$r and .deploy=="yes")] + [.clusters[] | select(.deploy=="yes")])[0].id')
  OBJ=$(v POST /object-storage "$(jq -n --argjson c "$CLUSTER" --arg l "$LABEL-files" '{cluster_id:$c, label:$l}')" | jq -r .object_storage.id)
fi
echo "   $OBJ"

echo "== Waiting for resources to become active"
for _ in $(seq 1 90); do
  I=$(v GET "/instances/$INSTANCE"); D=$(v GET "/databases/$DB"); O=$(v GET "/object-storage/$OBJ")
  IS=$(jq -r .instance.status <<<"$I"); DS=$(jq -r .database.status <<<"$D"); OS=$(jq -r .object_storage.status <<<"$O")
  echo "   instance=$IS database=$DS storage=$OS"
  [[ "$IS" == active && "$DS" == Running && "$OS" == active ]] && break
  sleep 20
done

IP=$(jq -r .instance.main_ip <<<"$I")
echo "== Restricting database access to the instance"
v PUT "/databases/$DB" "$(jq -n --arg ip "$IP/32" '{trusted_ips:[$ip]}')" >/dev/null || echo "   (set trusted sources in the console if this failed)"

cat <<EOF

Put these in deploy/.env:

DOMAIN=$IP.sslip.io
TOLLGATE_CORS_ORIGINS=https://$IP.sslip.io
TOLLGATE_DATABASE_URL=postgresql+psycopg://$(jq -r .database.user <<<"$D"):$(jq -r .database.password <<<"$D")@$(jq -r .database.host <<<"$D"):$(jq -r .database.port <<<"$D")/$(jq -r .database.dbname <<<"$D")?sslmode=require
TOLLGATE_S3_ENDPOINT=https://$(jq -r .object_storage.s3_hostname <<<"$O")
TOLLGATE_S3_ACCESS_KEY=$(jq -r .object_storage.s3_access_key <<<"$O")
TOLLGATE_S3_SECRET_KEY=$(jq -r .object_storage.s3_secret_key <<<"$O")

Then: rsync the repo to root@$IP, and run 'docker compose up -d --build' in deploy/.
EOF
