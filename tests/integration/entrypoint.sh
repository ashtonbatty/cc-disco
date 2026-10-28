#!/bin/bash
# Controller entrypoint: wait for targets, run the playbook with both
# ansible-core controllers, then validate the exported facts.
set -euo pipefail

cd /home/ansible/playbook
INVENTORY_DIR=tests/integration/inventory

echo "=== Waiting for target hosts to be reachable ==="
for host in el6-legacy el7-webserver el7-minimal el9-inventory el10-inventory ubuntu2404-inventory; do
    for i in $(seq 1 30); do
        if ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no \
               -i /home/ansible/.ssh/id_ecdsa \
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

# ansible-core 2.11 doesn't ship the yaml result format; use the plain default callback.
export ANSIBLE_STDOUT_CALLBACK=default

echo ""
echo "=== Running discovery playbook (ansible-core 2.11: EL6) ==="
/opt/ansible-2.11/bin/ansible-playbook -i "$INVENTORY_DIR/legacy.yml" gather_facts.yml -v

echo ""
echo "=== Running discovery playbook (ansible-core 2.16: EL7, EL9, EL10, Ubuntu) ==="
/opt/ansible-2.16/bin/ansible-playbook -i "$INVENTORY_DIR/modern.yml" gather_facts.yml -v

echo ""
echo "=== Validating exported facts ==="
/opt/ansible-2.16/bin/python tests/integration/validate.py output/facts

echo ""
echo "=== Integration tests PASSED ==="
