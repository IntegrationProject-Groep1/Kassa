#!/bin/bash
# Generates /etc/odoo/odoo.conf from environment variables before handing
# off to the official Odoo entrypoint. Mirrors what the Kubernetes init
# container does, so local dev and CI need no file bind-mount.
set -e

cat > /etc/odoo/odoo.conf <<EOF
[options]
admin_passwd = ${ODOO_MASTER_PASS:-admin}
addons_path = /mnt/extra-addons
data_dir = /var/lib/odoo
log_handler = werkzeug:WARNING
EOF

exec /entrypoint.sh "$@"
