# Public demo deployment

ClauseGrid has two server modes. Local mode remains loopback-only and exposes the reviewer gate.
Public mode is a constrained, synthetic-data demonstration behind an HTTPS proxy; browser approval
is disabled. It is not a production multi-tenant deployment.

## Render Blueprint

Prerequisites: the private GitHub repository, a Render account that can access it, and an API key
for the selected model provider. Render supports private Git repositories and Docker-based web
services; its proxy forwards public traffic to the port supplied in `PORT`.

1. Push the repository revision you intend to demo.
2. In Render, create a **Blueprint**, connect the private GitHub repository, and select
   `render.yaml`.
3. Supply the selected provider's key value as `CLAUSEGRID_API_KEY` when prompted. Do not put it in
   Git, Docker build arguments, or the image.
4. Deploy and open the generated `https://...onrender.com` URL.
5. Check `GET /healthz`, load the UI, select M10, and run one audit. The POST returns `202`; the UI
   polls an unguessable job URL until the result is complete.

The Blueprint starts with the user-selected Qubrid route and
`deepseek-ai/DeepSeek-V4-Flash`. These are ordinary `CLAUSEGRID_PROVIDER` and `CLAUSEGRID_MODEL`
environment values. Change them together only for a different provider/model route; keep the
matching Qubrid key value in `CLAUSEGRID_API_KEY`. Model-selection evidence documents that this
route is API-compatible but has not completed the full M10 manager/falsifier contract reliably. For
a custom OpenAI-compatible gateway set `CLAUSEGRID_PROVIDER=openai-compatible` and add
`CLAUSEGRID_BASE_URL`. The deployment entry point reads `RENDER_EXTERNAL_URL`, binds
`0.0.0.0:$PORT`, and stores transient artifacts under `/tmp/clausegrid`. Environment variables are
configured at runtime, not embedded into the container.

The selected model remains a demo profile rather than a production recommendation. Public users may
see a safe abstention, and a live audit can take several minutes. Use the repeated blind `agent-eval`
harness before making an accuracy or availability claim.

Official platform references:

- [Render web services](https://render.com/docs/web-services)
- [Render Docker deployments](https://render.com/docs/docker)
- [Render environment variables and secrets](https://render.com/docs/configure-environment-variables)
- [Render default environment variables](https://render.com/docs/environment-variables)
- [Render deploy and filesystem behavior](https://render.com/docs/deploys)

## Local container verification

Build without passing any credential into the build:

```powershell
docker build -t clausegrid:demo .
```

Run the image with runtime environment variables:

```powershell
docker run --rm -p 10000:10000 `
  -e CLAUSEGRID_API_KEY `
  -e CLAUSEGRID_PROVIDER=qubrid `
  -e CLAUSEGRID_MODEL=deepseek-ai/DeepSeek-V4-Flash `
  -e CLAUSEGRID_PUBLIC_ORIGIN=https://demo.example `
  -e PORT=10000 `
  clausegrid:demo
```

The exact public Host is deliberately enforced, so a local HTTP smoke request must set
`Host: demo.example`; `/healthz` is the only host-independent endpoint.

## Public-mode controls

- Only the repository's synthetic `WORKBOOK_CASES` and synthetic policy are addressable.
- One audit/approval may execute at a time; public audits run in background jobs.
- Defaults allow six audits globally and two per client per rolling hour.
- Modifying requests require the configured HTTPS Origin.
- Browser approval is disabled. `/api/approve` additionally requires
  `Authorization: Bearer $CLAUSEGRID_ADMIN_TOKEN`; an administrative client must also send the
  exact configured `Origin` header.
- Connections have a bounded socket read/write timeout and JSON request bodies are capped at 20 KB.
- Provider credentials and the administrator token stay server-side.
- Sealed evaluator vectors and oracle code are excluded from the public image; only the published
  aggregate legacy scorecard is copied for the UI summary.
- Public failures return generic text and a job ID; details are logged server-side.
- The image runs as UID/GID 10001.

## Deliberate operational limits

Run exactly one instance. Jobs, locks, sessions, and rate limits are held in process memory. The
default `/tmp` artifacts are ephemeral and may disappear on deploy or restart. A durable,
multi-instance service would require an authenticated identity layer, shared queue, shared rate
limiter, object storage with retention controls, encrypted audit log, worker isolation, and a
separate administrative review application. Those are outside the hackathon demo boundary rather
than silently claimed as complete.
