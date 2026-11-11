# AVA orchestrate SB688 gate configuration

AVA's orchestrate path calls the SB688 TypeScript pre-brain endpoint before the AVA brain. The AVA service must be configured with:

- SB688_RUNTIME_URL: HTTPS base URL of the SB688 deployment.
- SB688_GATE_SHARED_SECRET: same high-entropy secret configured in SB688, at least 32 characters.

SB688 must also have durable Ed25519 signing keys and a persistent SB688_PERMIT_REPLAY_STORE_PATH. See the SB688 deployment guide at docs/AVA_SB688_GATE_DEPLOYMENT.md.

The gate fails closed when the endpoint is missing, unreachable, returns an invalid response, uses an ephemeral key, or rejects the intent. Do not enable production traffic until the two services have been configured and the cross-service staging checks pass.
