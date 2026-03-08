.PHONY: test-integration integration-build integration-up integration-down integration-clean

COMPOSE := podman compose
SSH_KEY := ssh-keys/id_rsa

# ---------------------------------------------------------------------------
# SSH key generation (RSA for CentOS 6 compatibility — OpenSSH 5.3 lacks ed25519)
# ---------------------------------------------------------------------------
$(SSH_KEY):
	@mkdir -p ssh-keys
	ssh-keygen -t rsa -b 2048 -f $(SSH_KEY) -N "" -C "integration-test"

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

test-integration: $(SSH_KEY) integration-down integration-build integration-up

integration-build: $(SSH_KEY)
	$(COMPOSE) build

integration-up:
	$(COMPOSE) up --abort-on-container-exit --exit-code-from controller

integration-down:
	$(COMPOSE) down --volumes --remove-orphans 2>/dev/null || true

integration-clean: integration-down
	$(COMPOSE) down --rmi local --volumes --remove-orphans 2>/dev/null || true
	rm -rf ssh-keys/ output/
