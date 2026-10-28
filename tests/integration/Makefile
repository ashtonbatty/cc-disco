.PHONY: test-integration integration-build integration-up integration-down integration-clean

COMPOSE := podman compose
SSH_KEY := ssh-keys/id_ecdsa

# ---------------------------------------------------------------------------
# SSH key generation (ECDSA: OpenSSH 5.3 on CentOS 6 lacks ed25519 and rsa-sha2)
# ---------------------------------------------------------------------------
$(SSH_KEY):
	@mkdir -p ssh-keys
	ssh-keygen -t ecdsa -b 256 -f $(SSH_KEY) -N "" -C "integration-test"

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

test-integration: integration-down integration-build integration-up

integration-build: $(SSH_KEY)
	$(COMPOSE) build

integration-up:
	$(COMPOSE) up --abort-on-container-exit --exit-code-from controller

integration-down:
	$(COMPOSE) down --volumes --remove-orphans 2>/dev/null || true

integration-clean:
	$(COMPOSE) down --rmi local --volumes --remove-orphans 2>/dev/null || true
	rm -rf ssh-keys/ output/
