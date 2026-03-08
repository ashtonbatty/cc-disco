#!/bin/bash
# Controller entrypoint: wait for targets, run playbook, validate report.
set -euo pipefail

cd /home/ansible/playbook

echo "=== Waiting for target hosts to be reachable ==="
for host in el7-webserver el7-minimal el6-legacy; do
    for i in $(seq 1 30); do
        if ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no \
               -i /home/ansible/.ssh/id_rsa \
               ansible@"$host" true 2>/dev/null; then
            echo "  $host: reachable"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "  $host: TIMEOUT after 30 attempts"
            exit 1
        fi
        sleep 1
    done
done

echo ""
echo "=== Running discovery playbook ==="
# Override stdout_callback — ansible-core 2.11 doesn't ship the yaml callback
ANSIBLE_STDOUT_CALLBACK=default ansible-playbook \
    -i inventory/hosts.yml \
    gather_facts.yml \
    -v

echo ""
echo "=== Validating report ==="
python3 validate.py output/discovery_report.yml

echo ""
echo "=== Integration tests PASSED ==="
