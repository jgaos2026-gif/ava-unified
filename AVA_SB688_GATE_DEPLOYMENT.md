# AVA orchestrate SB688 gate configuration

AVA's `/orchestrate` path calls the SB688 TypeScript pre-brain endpoint before braid retrieval and before the AVA brain. Configure both services before enabling orchestration.

## AVA service

- `SB688_RUNTIME_URL`: HTTPS base URL of the SB688 deployment.
- `SB688_GATE_SHARED_SECRET`: the same high-entropy secret configured in SB688, at least 32 characters.

## SB688 service

- `SB688_GATE_SHARED_SECRET`: same secret as AVA.
- `SB688_SPINE_PRIVATE_KEY` or `SB688_SPINE_PRIVATE_KEY_FILE`: durable Ed25519 signing key.
- `SB688_SPINE_PUBLIC_KEY` or `SB688_SPINE_PUBLIC_KEY_FILE`: matching public key.
- `SB688_PERMIT_REPLAY_STORE_PATH`: writable persistent path for replay protection.

Keep key material and the shared secret in the hosting provider's secret manager, never in Git or chat. The replay store must survive process restarts and must be backed up with the service's durable state.

The gate fails closed when configuration is missing, the endpoint is unreachable, the response is invalid, the signing key is ephemeral, replay protection cannot persist, or SB688 rejects the intent.

## Staging acceptance test

1. Confirm both services report healthy and the SB688 runtime has durable key provenance.
2. Send a valid AVA orchestration request. Confirm the SB688 pre-brain check succeeds before the brain is called.
3. Send a request with an invalid/expired permit or a deliberately unavailable SB688 endpoint. Confirm AVA returns `GATE_REFUSED` and the brain call count remains zero.
4. Restart SB688 and repeat a replay attempt. Confirm the persisted replay store rejects it.
5. Only then enable production orchestration.

Passing unit tests does not prove production environment variables, network routing, TLS, database migrations, or durable storage are configured. Verify those in the deployed staging environment.
