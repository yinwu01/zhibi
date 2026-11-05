"""Transactional systemd unit replacement with a private remote rollback receipt."""
import base64
import uuid


def deployment(name, body):
    # Caller validates name and unit content before constructing this script.
    receipt = "/var/lib/zhibi/deployments/" + uuid.uuid4().hex
    path = "/etc/systemd/system/" + name + ".service"
    restore = '''#!/bin/sh
set -eu
cd "$(dirname "$0")"
systemctl disable --now NAME >/dev/null 2>&1 || true
if [ -f previous.service ]; then
    cp -p previous.service PATH
else
    rm -f PATH
fi
systemctl daemon-reload
if [ "$(cat enabled)" = enabled ]; then systemctl enable NAME; fi
if [ "$(cat active)" = active ]; then systemctl start NAME; fi
'''.replace('NAME', name).replace('PATH', path)
    script = '''set -eu
umask 077
receipt=RECEIPT
path=PATH
# Do not overwrite vendor units, aliases, drop-ins, or a currently masked service.
[ ! -L "$path" ]
[ ! -d "$path.d" ]
fragment=$(systemctl show -p FragmentPath --value NAME)
[ -z "$fragment" ] || [ "$fragment" = "$path" ]
mkdir -p /var/lib/zhibi/deployments
mkdir "$receipt"
if [ -f "$path" ]; then cp -p "$path" "$receipt/previous.service"; fi
systemctl is-enabled NAME > "$receipt/enabled" 2>/dev/null || true
systemctl is-active NAME > "$receipt/active" 2>/dev/null || true
printf %s RESTORE | base64 -d > "$receipt/rollback.sh"
chmod 700 "$receipt/rollback.sh"
printf %s BODY | base64 -d > "$receipt/next.service"
systemd-analyze verify "$receipt/next.service"
rollback() { result=$?; trap - EXIT; if [ "$result" != 0 ]; then sh "$receipt/rollback.sh"; fi; exit "$result"; }
trap rollback EXIT
install -m 600 "$receipt/next.service" "$path"
systemctl daemon-reload
systemctl enable NAME
systemctl restart NAME
sleep 2
systemctl is-active --quiet NAME
trap - EXIT
'''.replace('RECEIPT', receipt).replace('PATH', path).replace('NAME', name).replace('RESTORE', base64.b64encode(restore.encode()).decode()).replace('BODY', base64.b64encode(body.encode()).decode())
    return {"script": script, "receipt": receipt, "rollback": "sh " + receipt + "/rollback.sh"}
